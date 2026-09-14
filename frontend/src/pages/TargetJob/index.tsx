import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import type {
  AbilityItem,
  CapabilityGap,
  MatchResult,
  MatchResultPayload,
  TargetJobHome,
  TargetJobOut,
} from "../../api/client";
import Button from "../../components/ui/Button";
import Drawer from "../../components/ui/Drawer";
import ConfirmDialog from "../../components/ui/ConfirmDialog";
import EmptyState from "../../components/ui/EmptyState";
import { IllustrationTarget } from "../../components/ui/Illustrations";
import Icon from "../../components/ui/Icon";
import LoadingState from "../../components/ui/LoadingState";
import Tag from "../../components/ui/Tag";
import Textarea from "../../components/ui/Textarea";
import AiBadge from "../../components/AiBadge";
import SectionHeader from "../../components/ui/SectionHeader";

type Stage =
  | "loading"
  | "empty"
  | "editing" // pasting JD / before confirm
  | "confirmed" // JD confirmed, before match
  | "matched"; // match + gaps ready

const CATEGORY_LABEL: Record<string, string> = { hard: "硬技能", soft: "软技能", plus: "加分项" };
const CATEGORY_TONE: Record<string, "blue" | "green" | "orange"> = { hard: "blue", soft: "green", plus: "orange" };
const RELATION_ICON: Record<string, string> = { covered: "check", partial: "circle", missing: "x" };
const RELATION_TONE: Record<string, "green" | "orange" | "red"> = { covered: "green", partial: "orange", missing: "red" };
const RELATION_LABEL: Record<string, string> = { covered: "已覆盖", partial: "部分覆盖", missing: "待补齐" };
const PRIORITY_TONE: Record<string, "red" | "orange" | "gray"> = { high: "red", medium: "orange", low: "gray" };
const PRIORITY_LABEL: Record<string, string> = { high: "优先补齐", medium: "建议补齐", low: "可暂缓" };

export default function TargetJobPage() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage>("loading");
  const [home, setHome] = useState<TargetJobHome | null>(null);
  const [current, setCurrent] = useState<TargetJobOut | null>(null);
  const [match, setMatch] = useState<MatchResultPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // JD paste / parse editor
  const [rawJd, setRawJd] = useState("");
  const [draft, setDraft] = useState<TargetJobOut | null>(null); // parsed, unconfirmed
  const [parseStatus, setParseStatus] = useState<string>("");
  const [parsing, setParsing] = useState(false);
  // Phase 6.5-4.1: job title is a real editable input (sync from draft/current,
  // user edits are NOT overwritten because draft/current don't change on typing).
  const [jobTitle, setJobTitle] = useState("");

  useEffect(() => {
    setJobTitle((draft ?? current)?.job_title ?? "");
  }, [draft, current]);

  // job switcher drawer
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);

  // P0-2: incoming direction context from Explore (carried via ?direction_id=).
  // Effective context: URL param wins (the Explore seam), else the current
  // job's own DB-bound direction (refresh restore rule: URL > DB > none).
  const [searchParams] = useSearchParams();
  const directionIdParam = (() => {
    const v = searchParams.get("direction_id");
    const n = v ? Number(v) : NaN;
    return Number.isFinite(n) ? n : null;
  })();
  const [directionName, setDirectionName] = useState<string | null>(null);
  const effectiveDirId = directionIdParam ?? current?.direction_id;

  // decide stage from jd_status + match
  const decideStage = useCallback((tj: TargetJobOut, ms: TargetJobHome["match_summary"]) => {
    setCurrent(tj);
    if (tj.jd_status === "unparsed") {
      setStage("editing");
      setRawJd(tj.source_jd?.raw_text ?? "");
      setDraft(null);
      setMatch(null);
    } else if (tj.jd_status === "parsed") {
      // parsed draft: user must review + confirm before matching
      setStage("editing");
      setRawJd(tj.source_jd?.raw_text ?? "");
      setDraft(tj);
      setMatch(null);
    } else if (tj.jd_status === "user_edited" && ms) {
      setStage("matched");
      api.getTargetJobMatch(tj.target_job_id).then(setMatch).catch(() => setMatch(null));
    } else {
      // user_edited but no match yet
      setStage("confirmed");
      setMatch(null);
    }
  }, []);

  const reload = useCallback(() => {
    api
      .getTargetJobHome()
      .then((h) => {
        setHome(h);
        setCurrent(h.current);
        if (!h.current) {
          setStage("empty");
          setMatch(null);
          setDraft(null);
          return;
        }
        // decide stage from jd_status + match
        decideStage(h.current, h.match_summary);
      })
      .catch((e) => setError(e?.message ?? "加载失败"));
  }, [decideStage]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Resolve the direction name for the (effective) direction context banner.
  useEffect(() => {
    if (effectiveDirId == null) {
      setDirectionName(null);
      return;
    }
    let cancelled = false;
    api
      .getDirectionDetail(effectiveDirId)
      .then((d) => {
        if (!cancelled) setDirectionName(d.direction.name);
      })
      .catch(() => {
        if (!cancelled) setDirectionName(null);
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveDirId]);

  // ---- actions ----
  const startNewJob = () => {
    setStage("editing");
    setCurrent(null);
    setDraft(null);
    setRawJd("");
    setParseStatus("");
  };

  const handleParse = () => {
    const text = rawJd.trim();
    if (text.length < 10) {
      setError("请粘贴完整的岗位描述（JD），至少 10 个字");
      return;
    }
    setParsing(true);
    setError(null);
    const ensureJob = async () => {
      let jobId: number;
      if (current) {
        jobId = current.target_job_id;
      } else {
        // P0-2: bind the incoming direction so the Explore choice flows into
        // this job (and is shown after creation / on refresh via the job row).
        const created = await api.createTargetJob({ raw_jd: text, direction_id: effectiveDirId });
        jobId = created.target_job_id;
      }
      const resp = await api.parseTargetJobJD({ target_job_id: jobId, raw_jd: text, direction_id: effectiveDirId });
      setParseStatus(resp.parse_status);
      setDraft(resp.target_job);
      // keep editing stage; user must confirm
      reload();
    };
    ensureJob()
      .catch((e) => setError(e?.message ?? "解析失败"))
      .finally(() => setParsing(false));
  };

  const handleConfirm = () => {
    if (!draft) return;
    const am = draft.ability_model;
    setBusy(true);
    setError(null);
    api
      .confirmTargetJob(draft.target_job_id, {
        ability_model: am,
        industry: am.industry ?? draft.industry ?? "",
        responsibilities: am.responsibilities ?? draft.responsibilities ?? [],
        other_requirements: am.other_requirements ?? draft.other_requirements ?? [],
        job_title: jobTitle.trim() || draft.job_title,
        company: draft.company,
        city: draft.city,
      })
      .then((tj) => {
        setCurrent(tj);
        setDraft(null);
        setStage("confirmed");
        reload();
      })
      .catch((e) => setError(e?.message ?? "确认失败"))
      .finally(() => setBusy(false));
  };

  const handleRunMatch = () => {
    if (!current) return;
    setBusy(true);
    setError(null);
    api
      .runTargetJobMatch(current.target_job_id)
      .then((payload) => {
        setMatch(payload);
        setStage("matched");
        reload();
      })
      .catch((e) => setError(e?.message ?? "匹配失败"))
      .finally(() => setBusy(false));
  };

  const handleSwitch = (tj: TargetJobOut) => {
    setSwitcherOpen(false);
    if (current && tj.target_job_id === current.target_job_id) return;
    setError(null);
    // 「当前岗位」由后端按 updated_at 判定，切换 = set-current 触碰时间戳后
    // 重新加载；之前的实现只发 GET，切换从未真正生效。
    api
      .setCurrentTargetJob(tj.target_job_id)
      .then(() => reload())
      .catch((e) => setError(e?.message ?? "切换失败"));
  };

  // 从工作台（已确认/已匹配）主动进入编辑：以当前岗位为草稿，
  // 改完走同一条「确认并保存」；也可重新解析 JD（会覆盖能力模型草稿）。
  const startEditFromCurrent = () => {
    if (!current) return;
    setStage("editing");
    setDraft(current);
    setRawJd(current.source_jd?.raw_text ?? "");
    setMatch(null);
  };

  const handleDelete = () => {
    if (current) setConfirmDel(true);
  };

  const performDelete = () => {
    if (!current) return;
    api
      .deleteTargetJob(current.target_job_id)
      .then(() => {
        setConfirmDel(false);
        setCurrent(null);
        setMatch(null);
        setDraft(null);
        reload();
      })
      .catch((e) => setError(e?.message ?? "删除失败"));
  };

  // ---- render ----
  if (stage === "loading") return <LoadingState label="加载目标岗位…" />;

  const abilities = (draft ?? current)?.ability_model?.abilities ?? [];
  const isParsed = !!draft || (current && current.jd_status !== "unparsed");

  return (
    <div className="page tj-page">
      <div className="page-header tj-header">
        <div>
          <h1>目标岗位</h1>
          <p className="page-desc">
            选定一个具体岗位，AI 帮你解析 JD、判断个人匹配度、定位能力 Gap。分数由程序计算，AI 只负责解释。
          </p>
        </div>
        <div className="tj-header__actions">
          {(current || draft) && (
            <Button variant="ghost" size="sm" icon="refresh" onClick={reload}>刷新</Button>
          )}
          {home && home.items.length > 0 && (
            <Button variant="ghost" size="sm" icon="panel" onClick={() => setSwitcherOpen(true)}>
              岗位列表（{home.items.length}）
            </Button>
          )}
          {stage !== "empty" && (
            <Button variant="ghost" size="sm" icon="plus" onClick={startNewJob}>新建岗位</Button>
          )}
        </div>
      </div>

      {error && <div className="notice notice--error">{error}</div>}

      {/* P0-2: surface the direction context carried from Explore (or bound to
          the current job) so the user sees the cognitive link isn't lost. */}
      {effectiveDirId != null && (
        <div className="tj-dir-banner">
          <Icon name="target" size={16} />
          <span>
            来自职业探索 · <strong>{directionName ?? "加载中…"}</strong>
            <span className="muted">
              （{current && current.direction_id === effectiveDirId ? "已关联本岗位" : "解析 JD 后将关联到岗位"}）
            </span>
          </span>
        </div>
      )}

      {stage === "empty" && (
        <section className="tj-create">
          <EmptyState
            illustration={<IllustrationTarget />}
            title="还没有目标岗位"
            description="从探索里选中的方向，或者粘贴任意一份 JD，都能在这里建立你的岗位决策工作台。"
            action={
              <div className="tj-create__cta">
                <Button variant="primary" icon="plus" onClick={startNewJob}>粘贴 JD 新建岗位</Button>
              </div>
            }
          />
          <p className="tj-create__hint">
            还没有方向？先去 <button className="tj-link" onClick={() => navigate("/explore")}>职业探索</button> 找到你感兴趣的方向。
          </p>
        </section>
      )}

      {/* 编辑卡只在工作台前的 editing 阶段渲染。此前 matched 阶段也会渲染这张卡，
          但 draft 为 null 导致所有编辑静默丢失、确认无反应（假编辑器）。 */}
      {stage === "editing" && (
        <article className="tj-card">
          <header className="tj-card__head">
            <div className="tj-job-title">
              <Icon name="building" size={18} />
              <div>
                <div className="tj-job-title__main">
                  <input
                    className="tj-job-title__input"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    placeholder="填写岗位名称（可编辑）"
                    aria-label="岗位名称"
                  />
                  <span className="tj-job-title__company">{(draft ?? current)?.company || ""}</span>
                </div>
                <div className="tj-job-title__meta">
                  <Tag tone="gray">{(draft ?? current)?.city || "城市待定"}</Tag>
                  <Tag tone="blue">{(draft ?? current)?.industry || "行业待定"}</Tag>
                  <span className={`tj-status tj-status--${(draft ?? current)?.jd_status}`}>
                    {jdStatusLabel((draft ?? current)?.jd_status)}
                  </span>
                </div>
              </div>
            </div>
            {current && (
              <button className="tj-link tj-link--danger" onClick={handleDelete}>删除</button>
            )}
          </header>

          {/* JD 原文 / 解析 */}
          <section className="tj-section">
            <h2 className="tj-section__title">岗位描述（JD）</h2>
            <Textarea
              value={rawJd}
              onChange={(e) => setRawJd(e.target.value)}
              placeholder="粘贴岗位 JD 原文，AI 会帮你结构化解析出能力模型…"
              rows={6}
            />
            <div className="tj-section__actions">
              <Button variant="primary" size="sm" icon="sparkle" loading={parsing} onClick={handleParse}>
                解析 JD
              </Button>
              {parseStatus === "fallback" && (
                <span className="tj-fallback-note">
                  <Icon name="info" size={14} /> 当前为程序兜底解析（未连接 AI），确认后仍可手动编辑
                </span>
              )}
            </div>
          </section>

          {/* 解析结果 / 能力模型编辑 */}
          {isParsed && (
            <section className="tj-section">
              <h2 className="tj-section__title">
                岗位能力模型
                <span className="muted"> · 可手动增删改后再确认</span>
              </h2>
              <AbilityModelEditor
                abilities={abilities}
                onChange={(next) => setDraft((prev) => prev ? { ...prev, ability_model: { ...(prev.ability_model), abilities: next } } : prev)}
              />
              <div className="tj-section__actions">
                <Button variant="primary" size="sm" icon="check" loading={busy} onClick={handleConfirm} disabled={abilities.length === 0}>
                  确认并保存
                </Button>
                <span className="muted">确认后 AI 不覆盖你的结果，仅作为匹配依据</span>
              </div>
            </section>
          )}
        </article>
      )}

      {stage === "confirmed" && current && (
        <JobWorkspace tj={current} match={null} onRunMatch={handleRunMatch} busy={busy} navigate={navigate} onEdit={startEditFromCurrent} />
      )}

      {stage === "matched" && current && match && (
        <JobWorkspace tj={current} match={match} onRunMatch={handleRunMatch} busy={busy} navigate={navigate} onEdit={startEditFromCurrent} />
      )}

      {/* 岗位切换 Drawer */}
      <Drawer open={switcherOpen} onClose={() => setSwitcherOpen(false)} title="目标岗位列表">
        {home && (
          <div className="tj-switcher">
            {home.items.map((it) => (
              <button
                key={it.target_job_id}
                className={`tj-switcher__item ${current && it.target_job_id === current.target_job_id ? "is-active" : ""}`}
                onClick={() => handleSwitch(it)}
              >
                <div className="tj-switcher__title">{it.job_title || "（未命名岗位）"}</div>
                <div className="tj-switcher__meta">
                  <span>{it.company || "公司待定"}</span>
                  <Tag tone="gray">{jdStatusLabel(it.jd_status)}</Tag>
                </div>
              </button>
            ))}
          </div>
        )}
      </Drawer>

      <ConfirmDialog
        open={confirmDel}
        title="删除目标岗位"
        description={current ? `确认删除「${current.job_title || "未命名岗位"}」？此操作不可恢复。` : ""}
        confirmText="删除"
        danger
        onConfirm={performDelete}
        onClose={() => setConfirmDel(false)}
      />
    </div>
  );
}

// ----------------------------- JD 概览 + 匹配工作台 -----------------------------
function JobWorkspace({
  tj, match, onRunMatch, busy, navigate, onEdit,
}: {
  tj: TargetJobOut;
  match: MatchResultPayload | null;
  onRunMatch: () => void;
  busy: boolean;
  navigate: (to: string) => void;
  onEdit: () => void;
}) {
  const abilities = tj.ability_model?.abilities ?? [];
  const requirements = tj.ability_model?.requirements ?? { education: "", experience_years: 0, major: [], cert: [] };
  return (
    <div className="tj-workspace">
      {/* HERO：岗位身份 + 匹配分（页面最显著数据） */}
      <article className="tj-card card--hero tj-hero">
        <div className="tj-hero__id">
          <div className="tj-hero__eyebrow">目标岗位 · {jdStatusLabel(tj.jd_status)}</div>
          <h2 className="tj-hero__title">{tj.job_title || "（未命名岗位）"}</h2>
          <div className="tj-hero__sub">
            {tj.company || "公司待定"} · {tj.city || "城市待定"} · {tj.industry || "行业待定"}
          </div>
          <button className="tj-link" onClick={onEdit}>
            <Icon name="edit" size={13} /> 编辑 JD / 能力模型
          </button>
        </div>
        <div className="tj-hero__score">
          {match ? (
            <>
              <div className={`tj-score tj-score--${scoreTone(match.match.total_score)}`}>
                <span className="tj-score__num">{Math.round(match.match.total_score)}</span>
                <span className="tj-score__unit">分</span>
              </div>
              <div className="tj-hero__score-note">
                <div className="tj-match__verdict">{scoreVerdict(match.match.total_score)}</div>
                <div className="muted">由程序计算（加权覆盖度）</div>
                <AiBadge aiStatus={match.match.ai_status} />
              </div>
              <Button variant="ghost" size="sm" icon="refresh" loading={busy} onClick={onRunMatch}>
                重新匹配
              </Button>
            </>
          ) : (
            <Button variant="primary" icon="target" loading={busy} onClick={onRunMatch}>执行匹配</Button>
          )}
        </div>
      </article>

      {/* 一句话结论（仅由现有数据确定性组合，不新增 AI） */}
      {match && <p className="tj-verdict">{buildVerdict(match.match, match.gaps)}</p>}

      {/* 能力匹配（列表，不堆叠 Card） */}
      {match && (
        <section className="tj-section">
          <SectionHeader title="能力匹配" secondary />
          <div className="tj-match-list">
            {match.match.relation_judgements.map((r) => (
              <div key={r.ability} className="tj-match-row">
                <Icon name={RELATION_ICON[r.relation] ?? "info"} size={16} className={`tj-rel-icon tj-rel-icon--${r.relation}`} />
                <div className="tj-match-row__main">
                  <div className="tj-match-row__name">{r.ability}</div>
                  {r.reason && (
                    <p className="tj-match-row__reason">
                      <Icon name="sparkle" size={13} /> {r.reason}
                    </p>
                  )}
                </div>
                <div className="tj-match-row__side">
                  <Tag tone={RELATION_TONE[r.relation] ?? "gray"}>{RELATION_LABEL[r.relation] ?? r.relation}</Tag>
                  <span className="tj-relation__cat">{CATEGORY_LABEL[r.category] ?? r.category}</span>
                </div>
              </div>
            ))}
          </div>
          {match.match.dimension_scores?.length > 0 && (
            <div className="tj-dims">
              {match.match.dimension_scores.map((d) => (
                <div key={d.axis} className="tj-dim">
                  <div className="tj-dim__top">
                    <span>{d.axis}</span>
                    <span className="tj-dim__val">{Math.round(d.score)}</span>
                  </div>
                  <div className="tj-dim__bar">
                    <div className={`tj-dim__fill tj-dim__fill--${scoreTone(d.score)}`} style={{ width: `${d.score}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 关键 Gap（按优先级分组，第二视觉焦点） */}
      {match && match.gaps.length > 0 && (
        <section className="tj-section">
          <SectionHeader title={`关键 Gap（${match.gaps.length}）`} secondary />
          <GapGroups gaps={match.gaps} />
        </section>
      )}

      {/* JD 详细信息（降级为参考信息，flat / muted） */}
      <section className="tj-jd-flat">
        <div className="tj-jd-flat__head">岗位详情（参考）</div>
        <div className="tj-overview">
          <div className="tj-overview__row"><span className="tj-k">公司</span><span>{tj.company || "—"}</span></div>
          <div className="tj-overview__row"><span className="tj-k">岗位</span><span>{tj.job_title || "—"}</span></div>
          <div className="tj-overview__row"><span className="tj-k">行业</span><span>{tj.industry || "—"}</span></div>
          <div className="tj-overview__row"><span className="tj-k">学历</span><span>{requirements.education || "—"}</span></div>
          <div className="tj-overview__row"><span className="tj-k">经验</span><span>{requirements.experience_years ? `${requirements.experience_years} 年` : "—"}</span></div>
          {requirements.major?.length > 0 && (
            <div className="tj-overview__row">
              <span className="tj-k">专业</span>
              <div className="tj-tags">{requirements.major.map((m) => <Tag key={m} tone="gray">{m}</Tag>)}</div>
            </div>
          )}
        </div>
        {abilities.length > 0 && (
          <div className="tj-block">
            <h4 className="tj-block__h">岗位要求能力</h4>
            <div className="tj-tags">
              {abilities.map((a) => (
                <Tag key={a.name} tone={CATEGORY_TONE[a.category] ?? "gray"}>{a.name} · Lv.{a.level}</Tag>
              ))}
            </div>
          </div>
        )}
        {tj.responsibilities?.length > 0 && (
          <div className="tj-block">
            <h4 className="tj-block__h">核心职责</h4>
            <ul className="tj-list">{tj.responsibilities.map((r, i) => <li key={i}>{r}</li>)}</ul>
          </div>
        )}
        {tj.other_requirements?.length > 0 && (
          <div className="tj-block">
            <h4 className="tj-block__h">其他要求</h4>
            <div className="tj-tags">{tj.other_requirements.map((r, i) => <Tag key={i} tone="gray">{r}</Tag>)}</div>
          </div>
        )}
      </section>

      {/* AI 职责说明（诚实状态，不替用户决策） */}
      {match && (
        <div className="ai-block">
          <div className="ai-block-header"><AiBadge aiStatus={match.match.ai_status} label="AI 说明" /></div>
          <div className="ai-block-content muted">
            匹配分由程序基于你的画像与 JD 能力模型加权计算；AI 仅解释匹配依据与 Gap 来源，不替你做最终决定。
          </div>
        </div>
      )}

      {/* 下一步 */}
      <section className="next-step">
        <div className="next-step__text">
          <div className="next-step__title">下一步：去求职准备</div>
          <div className="next-step__desc">基于匹配结果补齐能力 Gap，或先把这次投递记录下来</div>
        </div>
        <div className="next-step__actions">
          <Button variant="primary" icon="arrowRight" onClick={() => navigate(`/prepare?target_job_id=${tj.target_job_id}`)}>
            进入求职准备
          </Button>
          <Button
            variant="secondary"
            icon="tracking"
            onClick={() =>
              navigate(
                `/tracking?company=${encodeURIComponent(tj.company)}` +
                  `&job=${encodeURIComponent(tj.job_title)}` +
                  `&city=${encodeURIComponent(tj.city)}` +
                  `&target_job_id=${tj.target_job_id}`
              )
            }
          >
            记录本次投递
          </Button>
        </div>
      </section>
    </div>
  );
}

// ----------------------------- 一句话结论（确定性组合，无新 AI） -----------------------------
function buildVerdict(match: MatchResult, gaps: CapabilityGap[]): string {
  const base = scoreVerdict(match.total_score);
  const strengths = match.relation_judgements
    .filter((r) => r.relation === "covered")
    .map((r) => r.ability)
    .slice(0, 2);
  const mainGap = gaps.find((g) => g.priority === "high")?.ability ?? gaps[0]?.ability;
  const parts = [base];
  if (strengths.length) parts.push(`主要优势集中在 ${strengths.join("、")}`);
  if (mainGap) parts.push(`当前主要 Gap 为 ${mainGap}`);
  return parts.join("，") + "。";
}

// ----------------------------- Gap 分组（按优先级） -----------------------------
function GapGroups({ gaps }: { gaps: CapabilityGap[] }) {
  const groups: [string, string][] = [
    ["high", "高优先级 Gap"],
    ["medium", "中优先级 Gap"],
    ["low", "可暂缓 Gap"],
  ];
  return (
    <div className="tj-gaps">
      {groups.map(([prio, label]) => {
        const items = gaps.filter((g) => g.priority === prio);
        if (!items.length) return null;
        return (
          <div className="tj-gap-group" key={prio}>
            <div className="tj-gap-group__title">{label}（{items.length}）</div>
            {items.map((g) => (
              <div key={g.gap_id} className={`tj-gap tj-gap--${prio}`}>
                <div className="tj-gap__head">
                  <span className="tj-gap__name">{g.ability}</span>
                  <Tag tone={PRIORITY_TONE[g.priority] ?? "gray"}>{PRIORITY_LABEL[g.priority] ?? g.priority}</Tag>
                </div>
                {g.why && <p className="tj-gap__why">{g.why}</p>}
                {g.evidence && <p className="tj-gap__evidence"><Icon name="evidence" size={13} /> {g.evidence}</p>}
                {g.improvement_direction && (
                  <p className="tj-gap__fix"><Icon name="bulb" size={13} /> {g.improvement_direction}</p>
                )}
                {!g.why && (
                  <p className="tj-gap__why tj-gap__why--na">AI 解释暂不可用，请稍后重试或手动补充判断。</p>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ----------------------------- 能力模型编辑器 -----------------------------
function AbilityModelEditor({
  abilities, onChange,
}: {
  abilities: AbilityItem[];
  onChange: (next: AbilityItem[]) => void;
}) {
  const update = (idx: number, patch: Partial<AbilityItem>) => {
    onChange(abilities.map((a, i) => (i === idx ? { ...a, ...patch } : a)));
  };
  const remove = (idx: number) => onChange(abilities.filter((_, i) => i !== idx));
  const add = () =>
    onChange([...abilities, { name: "", category: "hard", level: 3, weight: 1.0, requirement_type: "hard" }]);

  return (
    <div className="tj-editor">
      {abilities.map((a, idx) => (
        <div key={idx} className="tj-editor__row">
          <input
            className="tj-editor__name"
            value={a.name}
            placeholder="能力名称"
            onChange={(e) => update(idx, { name: e.target.value })}
          />
          <select
            className="tj-editor__cat"
            value={a.category}
            onChange={(e) => update(idx, { category: e.target.value, requirement_type: e.target.value })}
          >
            <option value="hard">硬技能</option>
            <option value="soft">软技能</option>
            <option value="plus">加分项</option>
          </select>
          <label className="tj-editor__lvl">
            级别
            <select value={a.level} onChange={(e) => update(idx, { level: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="tj-editor__w">
            权重
            <input
              type="number" step="0.1" min="0" max="2"
              value={a.weight}
              onChange={(e) => update(idx, { weight: Number(e.target.value) })}
            />
          </label>
          <button className="tj-editor__del" onClick={() => remove(idx)} aria-label="删除">
            <Icon name="x" size={14} />
          </button>
        </div>
      ))}
      <Button variant="ghost" size="sm" icon="plus" onClick={add}>添加能力</Button>
    </div>
  );
}

// ----------------------------- helpers -----------------------------
function jdStatusLabel(status?: string): string {
  const map: Record<string, string> = {
    unparsed: "待解析",
    parsing: "解析中",
    parsed: "已解析",
    user_edited: "已确认",
    fallback: "兜底解析",
  };
  return map[status ?? ""] ?? status ?? "未知";
}
function scoreTone(score: number): "green" | "blue" | "gray" {
  if (score >= 70) return "green";
  if (score >= 40) return "blue";
  return "gray";
}
function scoreVerdict(score: number): string {
  if (score >= 70) return "整体匹配度较高，核心要求基本覆盖";
  if (score >= 40) return "有一定基础，部分能力待补齐";
  return "当前匹配度偏低，建议优先补齐关键能力";
}
