import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type {
  CompareResult,
  CompareRow,
  DirectionDetail,
  DirectionOut,
  ExploreHome,
  ExploreState,
  IndustryDetail,
  JobDetail,
} from "../../api/client";
import Button from "../../components/ui/Button";
import Drawer from "../../components/ui/Drawer";
import EmptyState from "../../components/ui/EmptyState";
import { IllustrationProfile } from "../../components/ui/Illustrations";
import Icon from "../../components/ui/Icon";
import LoadingState from "../../components/ui/LoadingState";
import Tag from "../../components/ui/Tag";
import Textarea from "../../components/ui/Textarea";
import AiBadge from "../../components/AiBadge";

type View = "loading" | "no_profile" | "explore";

const EMPTY_STATE: ExploreState = {
  preferences: {},
  excluded_direction_ids: [],
  candidate_direction_ids: [],
  compare_direction_ids: [],
  target_direction_id: null,
};

/** Score -> human label (NOT a verdict; just a tint helper). */
function scoreTone(score: number): "green" | "blue" | "gray" {
  if (score >= 0.55) return "green";
  if (score >= 0.3) return "blue";
  return "gray";
}
function scoreLabel(score: number): string {
  if (score >= 0.55) return "较匹配";
  if (score >= 0.3) return "可了解";
  return "可参考";
}

export default function ExplorePage() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>("loading");
  const [home, setHome] = useState<ExploreHome | null>(null);
  const [error, setError] = useState<string | null>(null);

  // AI light-input
  const [preferenceText, setPreferenceText] = useState("");
  const [sending, setSending] = useState(false);

  // Drawer drill-down
  const [detailDirection, setDetailDirection] = useState<DirectionDetail | null>(null);
  const [industryDetail, setIndustryDetail] = useState<IndustryDetail | null>(null);
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null);

  // Compare view
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);

  const drawerBusy = useRef(false);
  const actionBusy = useRef(false);

  const reload = useCallback(() => {
    api
      .getExploreState()
      .then((h) => {
        setHome(h);
        setView(h.has_profile ? "explore" : "no_profile");
      })
      .catch((e) => setError(e?.message ?? "加载失败"));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // ---- actions ----
  const handlePreferenceSubmit = () => {
    const text = preferenceText.trim();
    if (!text) return;
    setSending(true);
    setError(null);
    api
      .postPreferenceText(text)
      .then((resp) => {
        setHome((prev) =>
          prev
            ? { ...prev, recommendations: resp.recommendations ?? prev.recommendations, state: resp.state }
            : prev
        );
        setPreferenceText("");
      })
      .catch((e) => setError(e?.message ?? "提交失败"))
      .finally(() => setSending(false));
  };

  const handleExclude = (d: DirectionOut, excluded: boolean) => {
    if (actionBusy.current) return;
    actionBusy.current = true;
    api
      .excludeDirection(d.direction_id, excluded)
      .then((resp) => {
        setHome((prev) => (prev ? { ...prev, recommendations: resp.recommendations ?? prev.recommendations, state: resp.state } : prev));
      })
      .catch((e) => setError(e?.message ?? "操作失败"))
      .finally(() => (actionBusy.current = false));
  };

  const handleToggleCandidate = (d: DirectionOut) => {
    if (actionBusy.current) return;
    actionBusy.current = true;
    api
      .toggleCandidate(d.direction_id)
      .then((resp) => {
        setHome((prev) => (prev ? { ...prev, state: resp.state } : prev));
      })
      .catch((e) => setError(e?.message ?? "操作失败"))
      .finally(() => (actionBusy.current = false));
  };

  const handleToggleCompare = (d: DirectionOut) => {
    if (!home || actionBusy.current) return;
    const inCompare = home.state.compare_direction_ids.includes(d.direction_id);
    if (!inCompare && home.state.compare_direction_ids.length >= 4) {
      setError("最多同时对比 4 个方向");
      return;
    }
    actionBusy.current = true;
    api
      .toggleCompare(d.direction_id)
      .then((resp) => {
        setHome((prev) => (prev ? { ...prev, state: resp.state } : prev));
      })
      .catch((e) => setError(e?.message ?? "操作失败"))
      .finally(() => (actionBusy.current = false));
  };

  const openCompareView = () => {
    if (!home) return;
    if (home.state.compare_direction_ids.length < 2) {
      setError("请先选择至少 2 个方向进行对比");
      return;
    }
    api.getCompare().then(setCompare).catch((e) => setError(e?.message ?? "对比加载失败"));
    setCompareOpen(true);
  };

  const openDirection = (d: DirectionOut) => {
    if (drawerBusy.current) return;
    drawerBusy.current = true;
    api
      .getDirectionDetail(d.direction_id)
      .then(setDetailDirection)
      .catch((e) => setError(e?.message ?? "加载失败"))
      .finally(() => (drawerBusy.current = false));
  };

  const openIndustry = (industryId: number) => {
    api
      .getIndustryDetail(industryId)
      .then(setIndustryDetail)
      .catch((e) => setError(e?.message ?? "行业详情加载失败"));
  };
  const openJob = (jobId: number) => {
    api
      .getJobDetail(jobId)
      .then(setJobDetail)
      .catch((e) => setError(e?.message ?? "岗位详情加载失败"));
  };

  const handleTarget = (d: DirectionOut) => {
    if (actionBusy.current) return;
    actionBusy.current = true;
    api
      .setTargetDirection(d.direction_id)
      .then((resp) => {
        setHome((prev) => (prev ? { ...prev, state: resp.state } : prev));
        // migrate to Target Job, carrying the chosen direction so the next stage
        // can show + bind it (P0-2: close the Explore -> Target Job seam).
        navigate(`/target-job?direction_id=${d.direction_id}`);
      })
      .catch((e) => setError(e?.message ?? "设置目标方向失败"))
      .finally(() => (actionBusy.current = false));
  };

  // ---- render ----
  if (view === "loading") return <LoadingState skeleton />;

  if (view === "no_profile") {
    return (
      <div className="page">
        <div className="page-header">
          <h1>职业探索</h1>
          <p className="page-desc">先建立你的职业画像，探索才能基于真实的你来推荐方向。</p>
        </div>
        <EmptyState
          illustration={<IllustrationProfile />}
          title="还没有职业画像"
          description="职业探索会根据你的能力、兴趣与经历推荐方向。请先完成职业画像。"
          action={
            <Button variant="primary" icon="arrowRight" onClick={() => navigate("/profile")}>
              去建立职业画像
            </Button>
          }
        />
      </div>
    );
  }

  const recs = home?.recommendations ?? [];
  const state = home?.state ?? EMPTY_STATE;
  const profile = home?.profile;

  return (
    <div className="page exp-page">
      <div className="page-header">
        <h1>职业探索</h1>
        <p className="page-desc">
          下面这些方向，是根据你的职业画像由程序计算并排序的。AI 只负责解释「为什么适合你」，最终方向由你决定。
        </p>
      </div>

      {error && <div className="notice notice--error">{error}</div>}

      {/* 第一层：画像摘要 */}
      {profile && <ProfileSummaryBar profile={profile} />}

      {/* 第二层：方向推荐（视觉中心，最先入眼） */}
      <section className="exp-recs">
        <div className="section-title-row">
          <h2 className="section-title">推荐方向</h2>
          <span className="muted">{recs.length} 个方向 · 按与你的匹配度排序</span>
        </div>
        {recs.length === 0 ? (
          <EmptyState icon="explore" title="暂无可推荐的方向" description="试着补充偏好，或检查画像是否足够完整。" />
        ) : (
          <div className="exp-rec-grid">
            {recs.map((d, idx) => {
              const inCompare = state.compare_direction_ids.includes(d.direction_id);
              const isCandidate = state.candidate_direction_ids.includes(d.direction_id);
              const tier = idx === 0 ? "top1" : idx === 1 ? "top2" : "";
              return (
                <article key={d.direction_id} className={`exp-card${tier ? ` exp-card--${tier}` : ""}`}>
                  {tier === "top1" && <span className="hero-eyebrow exp-card__rank">最推荐 · 优先了解</span>}
                  <header className="exp-card__head">
                    <button className="exp-card__title" onClick={() => openDirection(d)}>
                      {d.name}
                    </button>
                    <div className="exp-card__head-tags">
                      {tier === "top1" && <Tag tone="purple">最推荐</Tag>}
                      {tier === "top2" && <Tag tone="blue">推荐</Tag>}
                      <Tag tone={scoreTone(d.score)}>{scoreLabel(d.score)}</Tag>
                    </div>
                  </header>
                  <p className="exp-card__summary">{d.summary}</p>

                  <div className="exp-card__reason">
                    <Icon name="sparkle" size={14} />
                    <span>{d.reason || "（AI 暂不可用，已用程序生成匹配说明）"}</span>
                    <AiBadge aiStatus={d.reason_status} />
                  </div>

                  <div className="exp-card__basis">
                    {d.match_basis.slice(0, 2).map((b, i) => (
                      <span key={i} className="exp-basis">{b}</span>
                    ))}
                  </div>

                  <div className="exp-card__meta">
                    <div className="exp-meta-row">
                      <span className="exp-meta-k">核心能力</span>
                      <div className="exp-meta-v">{d.core_abilities.slice(0, 4).map((a) => <Tag key={a} tone="gray">{a}</Tag>)}</div>
                    </div>
                    <div className="exp-meta-row">
                      <span className="exp-meta-k">工作方式</span>
                      <div className="exp-meta-v">{d.work_styles.map((w) => <Tag key={w} tone="gray">{w}</Tag>)}</div>
                    </div>
                    {d.not_good_for.length > 0 && (
                      <div className="exp-meta-row">
                        <span className="exp-meta-k">不太适合</span>
                        <div className="exp-meta-v">{d.not_good_for.slice(0, 2).map((g) => <Tag key={g} tone="red">{g}</Tag>)}</div>
                      </div>
                    )}
                  </div>

                  <footer className="exp-card__actions">
                    <button className="exp-link" onClick={() => openDirection(d)}>
                      <Icon name="eye" size={14} /> 详情
                    </button>
                    <button className={`exp-link ${inCompare ? "is-on" : ""}`} onClick={() => handleToggleCompare(d)}>
                      <Icon name={inCompare ? "check" : "plus"} size={14} /> {inCompare ? "对比中" : "对比"}
                    </button>
                    <button className={`exp-link ${isCandidate ? "is-on" : ""}`} onClick={() => handleToggleCandidate(d)}>
                      <Icon name={isCandidate ? "check" : "plus"} size={14} /> {isCandidate ? "已收藏" : "收藏"}
                    </button>
                    <button className="exp-link exp-link--danger" onClick={() => handleExclude(d, true)}>
                      <Icon name="x" size={14} /> 不感兴趣
                    </button>
                  </footer>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* 第三层：轻量 AI 偏好入口（次级，不抢推荐中心） */}
      <section className="exp-ai-bar">
        <div className="exp-ai-bar__label">
          <Icon name="sparkle" size={16} />
          <span>想补充点什么？用一句话告诉 AI 你的偏好或排除项</span>
        </div>
        <div className="exp-ai-bar__input">
          <Textarea
            value={preferenceText}
            onChange={(e) => setPreferenceText(e.target.value)}
            placeholder="例如：我不想做纯技术，比较看重稳定，想去金融行业 / 我想留在上海"
            rows={2}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handlePreferenceSubmit();
            }}
          />
          <Button variant="primary" size="sm" loading={sending} onClick={handlePreferenceSubmit} disabled={!preferenceText.trim()}>
            更新偏好
          </Button>
        </div>
        {Object.keys(state.preferences).length > 0 && (
          <div className="exp-ai-bar__chips">
            {Object.entries(state.preferences).map(([k, v]) => {
              if (Array.isArray(v) && v.length) return v.map((x) => <Tag key={`${k}-${x}`} tone="blue">{String(x)}</Tag>);
              if (typeof v === "boolean" && v) return <Tag key={k} tone="green">{prefLabel(k)}</Tag>;
              if (typeof v === "string") return <Tag key={k} tone="blue">{String(v)}</Tag>;
              return null;
            })}
          </div>
        )}
      </section>

      {/* 第四层：对比托盘 */}
      {state.compare_direction_ids.length > 0 && (
        <div className="exp-compare-tray">
          <div className="exp-compare-tray__info">
            <Icon name="panel" size={16} />
            <span>已选择 {state.compare_direction_ids.length} 个方向进行对比</span>
          </div>
          <div className="exp-compare-tray__actions">
            <Button variant="ghost" size="sm" onClick={() => api.setCompare([]).then((r) => setHome((p) => (p ? { ...p, state: r.state } : p)))}>
              清空
            </Button>
            <Button variant="primary" size="sm" icon="arrowRight" onClick={openCompareView} disabled={state.compare_direction_ids.length < 2}>
              查看对比
            </Button>
          </div>
        </div>
      )}

      {/* 方向详情 Drawer */}
      <Drawer open={!!detailDirection} onClose={() => setDetailDirection(null)} title={detailDirection?.direction.name}>
        {detailDirection && (
          <DirectionDetailView
            detail={detailDirection}
            inCompare={state.compare_direction_ids.includes(detailDirection.direction.direction_id)}
            isCandidate={state.candidate_direction_ids.includes(detailDirection.direction.direction_id)}
            onToggleCompare={() => handleToggleCompare(detailDirection.direction)}
            onToggleCandidate={() => handleToggleCandidate(detailDirection.direction)}
            onExclude={() => handleExclude(detailDirection.direction, true)}
            onTarget={() => handleTarget(detailDirection.direction)}
            onIndustry={openIndustry}
            onJob={openJob}
          />
        )}
      </Drawer>

      {/* 行业详情 Drawer（叠加） */}
      <Drawer open={!!industryDetail} onClose={() => setIndustryDetail(null)} title={industryDetail?.name}>
        {industryDetail && (
          <div className="exp-detail">
            <p className="exp-detail__desc">{industryDetail.description}</p>
            <div className="exp-tags">{industryDetail.traits.map((t) => <Tag key={t} tone="blue">{t}</Tag>)}</div>
            <h4 className="exp-detail__h">常见岗位</h4>
            <div className="exp-job-list">
              {industryDetail.jobs.map((j) => (
                <button key={j.id} className="exp-job-item" onClick={() => openJob(j.id)}>
                  <span>{j.name}</span>
                  <Icon name="chevronRight" size={14} />
                </button>
              ))}
            </div>
          </div>
        )}
      </Drawer>

      {/* 岗位详情 Drawer（叠加） */}
      <Drawer open={!!jobDetail} onClose={() => setJobDetail(null)} title={jobDetail?.name}>
        {jobDetail && (
          <div className="exp-detail">
            <p className="exp-detail__desc">{jobDetail.description}</p>
            <div className="exp-meta-row">
              <span className="exp-meta-k">所需能力</span>
              <div className="exp-meta-v">{jobDetail.required_abilities.map((a) => <Tag key={a} tone="gray">{a}</Tag>)}</div>
            </div>
            <div className="exp-meta-row">
              <span className="exp-meta-k">入门门槛</span>
              <div className="exp-meta-v"><Tag tone="orange">{'★'.repeat(jobDetail.entry_barrier)}{'☆'.repeat(5 - jobDetail.entry_barrier)}</Tag></div>
            </div>
            <div className="exp-meta-row">
              <span className="exp-meta-k">工作方式</span>
              <div className="exp-meta-v">{jobDetail.work_styles.map((w) => <Tag key={w} tone="gray">{w}</Tag>)}</div>
            </div>
          </div>
        )}
      </Drawer>

      {/* 第五层：对比视图 Drawer */}
      <Drawer open={compareOpen} onClose={() => setCompareOpen(false)} title="方向对比">
        {compare && <CompareView compare={compare} />}
      </Drawer>

      {/* 下一步：去目标岗位 */}
      <section className="next-step">
        <div className="next-step__text">
          <div className="next-step__title">下一步：去目标岗位</div>
          <div className="next-step__desc">把一个感兴趣的方向，定为具体的目标岗位，开始匹配与准备</div>
        </div>
        <div className="next-step__actions">
          <Button variant="primary" icon="arrowRight" onClick={() => navigate("/target-job")}>
            去目标岗位
          </Button>
        </div>
      </section>
    </div>
  );
}

// ----------------------------- sub components -----------------------------
function prefLabel(key: string): string {
  const map: Record<string, string> = {
    value_stability: "看重稳定",
    value_growth: "看重成长",
    value_autonomy: "看重自主",
    value_social: "看重协作",
  };
  return map[key] ?? key;
}

function ProfileSummaryBar({ profile }: { profile: NonNullable<ExploreHome["profile"]> }) {
  return (
    <section className="exp-profile-bar">
      <div className="exp-profile-bar__who">
        <span className="exp-profile-bar__avatar"><Icon name="user" size={16} /></span>
        <div>
          <div className="exp-profile-bar__title">你是谁</div>
          <div className="exp-profile-bar__pos">{profile.positioning || "（画像定位待补充）"}</div>
        </div>
      </div>
      <div className="exp-profile-bar__cols">
        <div className="exp-profile-bar__col">
          <span className="exp-k">优势</span>
          <div>{profile.strengths.slice(0, 3).map((s) => <Tag key={s} tone="green">{s}</Tag>)}</div>
        </div>
        <div className="exp-profile-bar__col">
          <span className="exp-k">兴趣</span>
          <div>{profile.interest_tags.slice(0, 3).map((s) => <Tag key={s} tone="blue">{s}</Tag>)}</div>
        </div>
        <div className="exp-profile-bar__col">
          <span className="exp-k">能力</span>
          <div>{profile.ability_tags.slice(0, 3).map((s) => <Tag key={s} tone="gray">{s}</Tag>)}</div>
        </div>
      </div>
    </section>
  );
}

function DirectionDetailView({
  detail, inCompare, isCandidate, onToggleCompare, onToggleCandidate, onExclude, onTarget, onIndustry, onJob,
}: {
  detail: DirectionDetail;
  inCompare: boolean; isCandidate: boolean;
  onToggleCompare: () => void; onToggleCandidate: () => void; onExclude: () => void; onTarget: () => void;
  onIndustry: (id: number) => void; onJob: (id: number) => void;
}) {
  const d = detail.direction;
  return (
    <div className="exp-detail">
      <p className="exp-detail__desc">{d.description}</p>

      <div className="exp-card__reason">
        <Icon name="sparkle" size={14} />
        <span>{d.reason || "（AI 暂不可用，已用程序生成匹配说明）"}</span>
        <AiBadge aiStatus={d.reason_status} />
      </div>

      <h4 className="exp-detail__h">核心能力</h4>
      <div className="exp-tags">{d.core_abilities.map((a) => <Tag key={a} tone="gray">{a}</Tag>)}</div>

      <h4 className="exp-detail__h">工作方式</h4>
      <div className="exp-tags">{d.work_styles.map((w) => <Tag key={w} tone="gray">{w}</Tag>)}</div>

      <h4 className="exp-detail__h">不太适合</h4>
      <div className="exp-tags">{d.not_good_for.map((g) => <Tag key={g} tone="red">{g}</Tag>)}</div>

      <h4 className="exp-detail__h">发展路径</h4>
      <p className="exp-detail__desc">{d.growth_path}</p>

      <h4 className="exp-detail__h">涉及行业</h4>
      <div className="exp-job-list">
        {detail.industries.map((i) => (
          <button key={i.id} className="exp-job-item" onClick={() => onIndustry(i.id)}>
            <span>{i.name}</span>
            <Icon name="chevronRight" size={14} />
          </button>
        ))}
      </div>

      <h4 className="exp-detail__h">常见岗位</h4>
      <div className="exp-job-list">
        {detail.jobs.map((j) => (
          <button key={j.id} className="exp-job-item" onClick={() => onJob(j.id)}>
            <span>{j.name}</span>
            <Icon name="chevronRight" size={14} />
          </button>
        ))}
      </div>

      <div className="exp-detail__actions">
        <Button variant={isCandidate ? "secondary" : "ghost"} size="sm" icon="plus" onClick={onToggleCandidate}>
          {isCandidate ? "已收藏" : "收藏"}
        </Button>
        <Button variant={inCompare ? "secondary" : "ghost"} size="sm" icon="plus" onClick={onToggleCompare}>
          {inCompare ? "对比中" : "加入对比"}
        </Button>
        <Button variant="danger" size="sm" icon="x" onClick={onExclude}>不感兴趣</Button>
        <Button variant="primary" size="sm" icon="target" onClick={onTarget}>设为发展目标</Button>
      </div>
    </div>
  );
}

function CompareView({ compare }: { compare: CompareResult }) {
  const rows = compare.rows;
  const dims: { key: keyof CompareRow; kind: "text" | "tags" | "score"; label: string }[] = [
    { key: "summary", kind: "text", label: "一句话" },
    { key: "core_abilities", kind: "tags", label: "核心能力" },
    { key: "work_styles", kind: "tags", label: "工作方式" },
    { key: "not_good_for", kind: "tags", label: "不太适合" },
    { key: "growth_path", kind: "text", label: "发展路径" },
    { key: "score", kind: "score", label: "匹配度" },
  ];
  return (
    <div className="exp-compare" style={{ ["--exp-cols" as string]: rows.length } as React.CSSProperties}>
      <div className="exp-compare__advice">
        <Icon name="bulb" size={16} />
        <div>
          {compare.advice.length ? (
            compare.advice.map((a, i) => <p key={i}>{a}</p>)
          ) : (
            <p>这几个方向各有侧重，结合你更看重的价值来选。</p>
          )}
        </div>
      </div>

      <div className="exp-compare__head">
        <div className="exp-compare__corner" />
        {rows.map((r) => (
          <div key={r.direction_id} className="exp-compare__colhead">{r.name}</div>
        ))}
      </div>

      {dims.map((dim) => (
        <div key={String(dim.key)} className="exp-compare__row">
          <div className="exp-compare__label">{dim.label}</div>
          {rows.map((r) => (
            <div key={r.direction_id} className="exp-compare__cell">
              {dim.key === "score" ? (
                <Tag tone={scoreTone(r.score)}>{scoreLabel(r.score)}</Tag>
              ) : dim.kind === "tags" ? (
                <div className="exp-cell-tags">
                  {(r[dim.key] as string[]).slice(0, 3).map((x) => (
                    <Tag key={x} tone={dim.key === "not_good_for" ? "red" : "gray"}>{x}</Tag>
                  ))}
                </div>
              ) : (
                <span className="exp-compare__text">{(r[dim.key] as string) || "—"}</span>
              )}
            </div>
          ))}
        </div>
      ))}

      <p className="exp-compare__note">对比只帮你看清差异，不替你下结论。选哪个方向，由你决定。</p>
    </div>
  );
}
