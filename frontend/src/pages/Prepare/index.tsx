import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import type {
  InterviewFocusItem,
  PrepGap,
  PrepHome,
  PrepPlan,
  PrepTask,
  ResumeAdviceItem,
  TargetJobOut,
} from "../../api/client";
import Button from "../../components/ui/Button";
import AiBadge from "../../components/AiBadge";
import Tag from "../../components/ui/Tag";
import Tabs from "../../components/ui/Tabs";
import Progress from "../../components/ui/Progress";
import EmptyState from "../../components/ui/EmptyState";
import { IllustrationPrepare } from "../../components/ui/Illustrations";
import LoadingState from "../../components/ui/LoadingState";
import Icon from "../../components/ui/Icon";
import Textarea from "../../components/ui/Textarea";
import Select from "../../components/ui/Select";

type TabKey = "plan" | "interview" | "resume";

const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };
const PRIORITY_LABEL: Record<string, string> = { high: "P0 优先", medium: "P1", low: "P2" };
const PRIORITY_TONE: Record<string, "red" | "orange" | "blue"> = {
  high: "red",
  medium: "orange",
  low: "blue",
};
const EVIDENCE_TONE: Record<string, "green" | "orange" | "gray"> = {
  sufficient: "green",
  insufficient: "orange",
  none: "gray",
};
const EVIDENCE_LABEL: Record<string, string> = {
  sufficient: "证据充分",
  insufficient: "证据不足",
  none: "暂无证据",
};
const ADVICE_TONE: Record<string, "blue" | "orange" | "green" | "gray"> = {
  highlight: "blue",
  evidence_gap: "orange",
  keyword: "green",
  weak_link: "gray",
};
const ADVICE_LABEL: Record<string, string> = {
  highlight: "突出经历",
  evidence_gap: "证据不足",
  keyword: "关键词",
  weak_link: "弱关联",
};
const SEVERITY_TONE: Record<string, "red" | "orange" | "gray"> = {
  high: "red",
  medium: "orange",
  low: "gray",
};

function sortTasks(tasks: PrepTask[]): PrepTask[] {
  return [...tasks].sort((a, b) => {
    const p = (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9);
    if (p !== 0) return p;
    if (a.status !== b.status) return a.status === "done" ? 1 : -1;
    return a.order - b.order;
  });
}

export default function PreparePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // P1-2: which target job to prepare for. From URL (?target_job_id=) when
  // arriving from Target Job; else null -> backend falls back to latest.
  const initialTjId = (() => {
    const v = searchParams.get("target_job_id");
    const n = v ? Number(v) : NaN;
    return Number.isFinite(n) ? n : null;
  })();
  const [targetJobId, setTargetJobId] = useState<number | null>(initialTjId);
  const [jobList, setJobList] = useState<TargetJobOut[]>([]);

  const [home, setHome] = useState<PrepHome | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>("plan");
  const [genPlan, setGenPlan] = useState(false);
  const [genInterview, setGenInterview] = useState(false);
  const [genResume, setGenResume] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingTasks, setSavingTasks] = useState<Set<number>>(new Set());

  const load = useCallback((tjId?: number | null) => {
    setLoading(true);
    setError(null);
    api
      .getPrepHome(tjId ?? undefined)
      .then((h) => {
        setHome(h);
        if (tjId != null) setTargetJobId(tjId);
      })
      .catch((e) => setError(e?.message || "加载失败"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(targetJobId);
  }, [load, targetJobId]);

  // Fetch the list of target jobs so the user can switch which one to prep for.
  useEffect(() => {
    if (!home?.has_target) {
      setJobList([]);
      return;
    }
    api
      .getTargetJobHome()
      .then((h) => setJobList(h.items ?? []))
      .catch(() => setJobList([]));
  }, [home?.has_target]);

  const handleSwitchJob = (id: number) => {
    if (id === targetJobId) return;
    // Persist the choice in the URL so refresh keeps the same job (P1-2).
    setSearchParams({ target_job_id: String(id) });
    load(id);
  };

  const tjId = home?.target_job?.target_job_id;

  const handleGeneratePlan = useCallback(() => {
    if (!tjId) return;
    setGenPlan(true);
    setError(null);
    api
      .generatePrepPlan(tjId)
      .then((r) => {
        setHome((h) => (h ? { ...h, prep_plan: r.prep_plan, tasks: r.tasks, prep_stale: false } : h));
      })
      .catch((e) => setError(e?.message || "生成准备计划失败"))
      .finally(() => setGenPlan(false));
  }, [tjId]);

  const handleGenerateInterview = useCallback(() => {
    if (!tjId) return;
    setGenInterview(true);
    setError(null);
    api
      .generateInterviewFocus(tjId)
      .then((r) => {
        setHome((h) => (h ? { ...h, interview_focus: r.interview_focus, interview_stale: false } : h));
        setActiveTab("interview");
      })
      .catch((e) => setError(e?.message || "生成面试重点失败"))
      .finally(() => setGenInterview(false));
  }, [tjId]);

  const handleGenerateResume = useCallback(() => {
    if (!tjId) return;
    setGenResume(true);
    setError(null);
    api
      .generateResumeAdvice(tjId)
      .then((r) => {
        setHome((h) => (h ? { ...h, resume_advice: r.resume_advice, resume_stale: false } : h));
        setActiveTab("resume");
      })
      .catch((e) => setError(e?.message || "生成简历建议失败"))
      .finally(() => setGenResume(false));
  }, [tjId]);

  const patchTask = useCallback(
    (taskId: number, fields: Record<string, unknown>) => {
      setSavingTasks((s) => new Set(s).add(taskId));
      api
        .updatePrepTask(taskId, fields)
        .then((r) => {
          setHome((h) => {
            if (!h) return h;
            const tasks = h.tasks.map((t) => (t.task_id === taskId ? r.task : t));
            const plan = r.task.status // progress recalculated server-side
              ? { ...(h.prep_plan as PrepPlan) }
              : h.prep_plan;
            return { ...h, tasks, prep_plan: plan };
          });
        })
        .catch((e) => setError(e?.message || "更新任务失败"))
        .finally(() => {
          setSavingTasks((s) => {
            const n = new Set(s);
            n.delete(taskId);
            return n;
          });
        });
    },
    []
  );

  if (loading) return <LoadingState label="加载准备工作台…" />;

  if (!home || !home.has_target) {
    return (
      <div className="page">
        <div className="page-header">
          <h1 className="page-title">求职准备</h1>
        </div>
        <EmptyState
          icon="target"
          title="还没有目标岗位"
          description="先到「目标岗位」工作区粘贴 JD、完成匹配与 Gap 分析，这里会自动生成你的准备计划。"
        />
      </div>
    );
  }

  if (!home.has_match) {
    return (
      <div className="page">
        <div className="page-header">
          <h1 className="page-title">求职准备</h1>
        </div>
        <EmptyState
          icon="target"
          title="还没有完成岗位匹配"
          description="请先在「目标岗位」工作区运行匹配，生成能力 Gap 后，才能进入准备阶段。"
          action={
            <Button icon="arrowRight" onClick={() => navigate("/target-job")}>
              去目标岗位
            </Button>
          }
        />
      </div>
    );
  }

  const tj = home.target_job!;
  const plan = home.prep_plan;
  const tasks = sortTasks(home.tasks);
  const gaps = home.gaps;
  const gapByAbility = new Map<string, PrepGap>(gaps.map((g) => [g.ability, g]));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">求职准备</h1>
          <p className="page-subtitle">基于能力 Gap，生成你可以执行的准备方案。</p>
        </div>
        {/* P1-2: switch which target job to prepare for (only when several). */}
        {jobList.length > 1 && tjId != null && (
          <div className="pj-job-switch">
            <span className="muted">目标岗位</span>
            <Select
              value={String(tjId)}
              options={jobList.map((j) => ({
                value: String(j.target_job_id),
                label: `${j.job_title || "未命名岗位"}${j.company ? " · " + j.company : ""}`,
              }))}
              onChange={(e) => handleSwitchJob(Number(e.target.value))}
            />
          </div>
        )}
      </div>

      {error && (
        <div className="pj-banner pj-banner--error">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Top: target job summary + match + progress */}
      <section className="pj-summary">
        <div className="pj-summary__main">
          <div className="pj-summary__title">
            <Icon name="building" size={18} />
            <span>{tj.job_title || "未命名岗位"}</span>
            {tj.company && <span className="pj-summary__company">@ {tj.company}</span>}
          </div>
          <div className="pj-summary__meta">
            {tj.industry && <Tag tone="gray">{tj.industry}</Tag>}
            {home.match_summary && (
              <Tag tone="gray">匹配度 {Math.round(home.match_summary.total_score)}%</Tag>
            )}
            {home.match_summary && (
              <Tag tone="orange">{home.match_summary.gap_count} 项能力 Gap</Tag>
            )}
          </div>
        </div>
        <div className="pj-summary__progress">
          {plan ? (
            <Progress
              label="准备进度"
              value={plan.overall_progress}
              showValue
            />
          ) : (
            <span className="pj-summary__empty">尚未生成准备计划</span>
          )}
          <div className="pj-summary__cta">
            <Button
              variant="secondary"
              size="sm"
              icon="tracking"
              onClick={() =>
                navigate(
                  `/tracking?company=${encodeURIComponent(tj.company || "")}` +
                    `&job=${encodeURIComponent(tj.job_title || "")}` +
                    `&city=${encodeURIComponent(tj.city || "")}` +
                    `&target_job_id=${tj.target_job_id}`
                )
              }
            >
              记录本次投递
            </Button>
          </div>
        </div>
      </section>

      {/* Stale banner */}
      {(home.prep_stale || home.interview_stale || home.resume_stale) && (
        <div className="pj-banner pj-banner--warn">
          <Icon name="refresh" size={16} />
          <span>当前内容与上一次匹配结果不一致，建议重新生成以保证建议准确。</span>
        </div>
      )}

      <Tabs
        tabs={[
          { key: "plan", label: "准备计划" },
          { key: "interview", label: "面试重点" },
          { key: "resume", label: "简历建议" },
        ]}
        active={activeTab}
        onChange={(k) => setActiveTab(k as TabKey)}
      />

      {/* ---------------- F12: preparation plan ---------------- */}
      {activeTab === "plan" && (
        <div className="pj-section">
          {!plan ? (
            <EmptyState
              illustration={<IllustrationPrepare />}
              icon="prepare"
              title="还没有准备计划"
              description="系统会基于你的能力 Gap，生成一份可执行的准备清单（含优先级与完成进度）。"
              action={
                <Button icon="sparkles" loading={genPlan} onClick={handleGeneratePlan}>
                  生成准备计划
                </Button>
              }
            />
          ) : (
            <>
              <div className="pj-section__head">
                <h2 className="pj-section__title">
                  优先准备事项
                  <span className="pj-section__count">{tasks.length} 项</span>
                  {plan && <AiBadge aiStatus={plan.ai_status as "ok" | "fallback"} />}
                </h2>
                <div className="pj-section__actions">
                  {home.prep_stale && (
                    <Button variant="secondary" size="sm" icon="refresh" loading={genPlan} onClick={handleGeneratePlan}>
                      重新生成
                    </Button>
                  )}
                </div>
              </div>
              {tasks.length === 0 ? (
                <EmptyState
                  icon="check"
                  title="没有需要补齐的能力"
                  description="当前匹配结果中暂无未覆盖的能力 Gap，可以直接进入下一步。"
                />
              ) : (
                <div className="pj-tasks">
                  {tasks.map((t) => (
                    <PrepTaskCard
                      key={t.task_id}
                      task={t}
                      gap={gapByAbility.get(t.ability)}
                      saving={savingTasks.has(t.task_id)}
                      onPatch={patchTask}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ---------------- F14: interview focus ---------------- */}
      {activeTab === "interview" && (
        <div className="pj-section">
          <div className="pj-section__head">
            <h2 className="pj-section__title">
              面试重点
              <span className="pj-section__count">{home.interview_focus.length} 项</span>
              {home.interview_focus.length > 0 && (
                <AiBadge aiStatus={home.interview_focus[0]?.ai_status} />
              )}
            </h2>
            <div className="pj-section__actions">
              <Button
                variant="secondary"
                size="sm"
                icon="sparkles"
                loading={genInterview}
                onClick={handleGenerateInterview}
              >
                {home.interview_focus.length ? "重新生成" : "生成面试重点"}
              </Button>
            </div>
          </div>
          {home.interview_focus.length === 0 ? (
            <EmptyState
              icon="message"
              title="还没有面试重点"
              description="基于岗位要求与你的真实经历，预测可能被重点问到的问题与回答建议。"
            />
          ) : (
            <div className="pj-focus-list">
              {home.interview_focus.map((f) => (
                <InterviewFocusCard key={f.focus_id} item={f} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ---------------- F13: resume advice ---------------- */}
      {activeTab === "resume" && (
        <div className="pj-section">
          <div className="pj-section__head">
            <h2 className="pj-section__title">
              简历建议
              <span className="pj-section__count">{home.resume_advice.length} 项</span>
              {home.resume_advice.length > 0 && (
                <AiBadge aiStatus={home.resume_advice[0]?.ai_status} />
              )}
            </h2>
            <div className="pj-section__actions">
              <Button
                variant="secondary"
                size="sm"
                icon="sparkles"
                loading={genResume}
                onClick={handleGenerateResume}
              >
                {home.resume_advice.length ? "重新生成" : "生成简历建议"}
              </Button>
            </div>
          </div>
          {home.resume_advice.length === 0 ? (
            <EmptyState
              icon="fileText"
              title="还没有简历建议"
              description="针对这个岗位，给出轻量的简历调整建议（突出经历 / 补强证据 / 关键词 / 弱关联）。"
            />
          ) : (
            <div className="pj-advice-list">
              {home.resume_advice.map((a) => (
                <ResumeAdviceCard key={a.advice_id} item={a} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* 下一步：去求职追踪 */}
      <section className="next-step">
        <div className="next-step__text">
          <div className="next-step__title">下一步：去求职追踪</div>
          <div className="next-step__desc">把这份岗位的实际投递记录下来，追踪面试与进度</div>
        </div>
        <div className="next-step__actions">
          <Button
            variant="primary"
            icon="arrowRight"
            onClick={() =>
              navigate(
                `/tracking?company=${encodeURIComponent(tj.company || "")}` +
                  `&job=${encodeURIComponent(tj.job_title || "")}` +
                  `&city=${encodeURIComponent(tj.city || "")}` +
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

// ----------------------------- prep task card -----------------------------
function PrepTaskCard({
  task,
  gap,
  saving,
  onPatch,
}: {
  task: PrepTask;
  gap: PrepGap | undefined;
  saving: boolean;
  onPatch: (id: number, fields: Record<string, unknown>) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [note, setNote] = useState(task.user_note);

  const done = task.status === "done";

  return (
    <div className={`pj-task ${done ? "pj-task--done" : ""}`}>
      <div className="pj-task__head">
        <button
          className={`pj-check ${done ? "pj-check--on" : ""}`}
          aria-label={done ? "标记为未完成" : "标记为已完成"}
          onClick={() => onPatch(task.task_id, { status: done ? "pending" : "done" })}
          disabled={saving}
        >
          {done && <Icon name="check" size={14} />}
        </button>
        <div className="pj-task__heading">
          <div className="pj-task__title">
            <Tag tone="gray">{task.ability}</Tag>
            <span className={`pj-task__name ${done ? "pj-task__name--done" : ""}`}>
              {task.title || task.ability}
            </span>
          </div>
          <div className="pj-task__sub">
            <Tag tone={PRIORITY_TONE[task.priority] || "blue"}>
              {PRIORITY_LABEL[task.priority] || task.priority}
            </Tag>
            {gap && <Tag tone="orange">Gap {Math.round(gap.gap_degree * 100)}%</Tag>}
            {task.is_user_edited && <Tag tone="gray">已手动调整</Tag>}
          </div>
        </div>
        <div className="pj-task__ops">
          <Select
            className="pj-task__priority"
            value={task.priority}
            options={[
              { value: "high", label: "P0 优先" },
              { value: "medium", label: "P1" },
              { value: "low", label: "P2" },
            ]}
            onChange={(e) => onPatch(task.task_id, { priority: e.target.value })}
            disabled={saving}
          />
          <button className="pj-task__toggle" onClick={() => setExpanded((v) => !v)}>
            <Icon name="chevronRight" size={16} className={expanded ? "pj-task__toggle--open" : ""} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="pj-task__body">
          {task.reason && (
            <p className="pj-task__line">
              <span className="pj-task__label">为什么准备</span>
              {task.reason}
            </p>
          )}
          {task.current_situation && (
            <p className="pj-task__line">
              <span className="pj-task__label">当前情况</span>
              {task.current_situation}
            </p>
          )}
          {task.action_suggestion && (
            <p className="pj-task__line pj-task__line--action">
              <span className="pj-task__label">
                <Icon name="bulb" size={13} /> 建议行动
              </span>
              {task.action_suggestion}
            </p>
          )}
          <div className="pj-task__note">
            <label className="field-label">我的备注</label>
            <Textarea
              value={note}
              placeholder="记录你的准备进度、资源或想法…"
              rows={2}
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="actions">
              <Button
                size="sm"
                variant="secondary"
                loading={saving}
                onClick={() => onPatch(task.task_id, { user_note: note })}
              >
                保存备注
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ----------------------------- interview focus card -----------------------------
function InterviewFocusCard({ item }: { item: InterviewFocusItem }) {
  return (
    <div className="pj-focus">
      <div className="pj-focus__q">
        <Icon name="evidence" size={16} />
        <span>{item.question}</span>
        <Tag tone={EVIDENCE_TONE[item.evidence_status] || "gray"}>
          {EVIDENCE_LABEL[item.evidence_status] || item.evidence_status}
        </Tag>
      </div>
      {item.related_requirement && (
        <p className="pj-focus__row">
          <span className="pj-focus__k">对应要求</span>
          {item.related_requirement}
        </p>
      )}
      {item.related_experience && (
        <p className="pj-focus__row">
          <span className="pj-focus__k">可回答经历</span>
          {item.related_experience}
        </p>
      )}
      {item.reason && <p className="pj-focus__row pj-focus__row--muted">{item.reason}</p>}
      {item.preparation_advice && (
        <p className="pj-focus__row pj-focus__row--action">
          <Icon name="bulb" size={13} /> {item.preparation_advice}
        </p>
      )}
    </div>
  );
}

// ----------------------------- resume advice card -----------------------------
function ResumeAdviceCard({ item }: { item: ResumeAdviceItem }) {
  return (
    <div className="pj-advice">
      <div className="pj-advice__head">
        <Tag tone={ADVICE_TONE[item.advice_type] || "gray"}>
          {ADVICE_LABEL[item.advice_type] || item.advice_type}
        </Tag>
        <Tag tone={SEVERITY_TONE[item.severity] || "gray"}>{item.severity}</Tag>
      </div>
      <p className="pj-advice__content">{item.content}</p>
      {item.related_experience && (
        <p className="pj-advice__rel">相关经历：{item.related_experience}</p>
      )}
      {item.related_gap && (
        <p className="pj-advice__rel">相关 Gap：{item.related_gap}</p>
      )}
    </div>
  );
}
