import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import type {
  ApplicationDetail,
  ApplicationOut,
  ApplicationStatus,
  InterviewOut,
  TrackingOverview,
} from "../../api/client";
import Button from "../../components/ui/Button";
import Tag from "../../components/ui/Tag";
import Drawer from "../../components/ui/Drawer";
import Input from "../../components/ui/Input";
import Select from "../../components/ui/Select";
import Textarea from "../../components/ui/Textarea";
import EmptyState from "../../components/ui/EmptyState";
import LoadingState from "../../components/ui/LoadingState";
import Icon from "../../components/ui/Icon";
import ConfirmDialog from "../../components/ui/ConfirmDialog";
import { IllustrationTracking } from "../../components/ui/Illustrations";
import { useToast } from "../../components/ui/Toast";

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  drafted: "草稿",
  applied: "已投递",
  written_test: "笔试中",
  interviewing: "面试中",
  offer_received: "已拿 Offer",
  rejected: "未通过",
  withdrawn: "已放弃",
};
/** 反向查表：后端 overview.counts_labeled 的键是中文标签，而筛选要的是状态枚举值。 */
const LABEL_TO_STATUS = Object.fromEntries(
  (Object.entries(STATUS_LABELS) as [ApplicationStatus, string][]).map(([k, v]) => [v, k])
) as Record<string, ApplicationStatus>;
const STATUS_TONE: Record<ApplicationStatus, "gray" | "blue" | "orange" | "green" | "red"> = {
  drafted: "gray",
  applied: "blue",
  written_test: "blue",
  interviewing: "orange",
  offer_received: "green",
  rejected: "red",
  withdrawn: "gray",
};
// Allowed transitions (mirrors backend _ALLOWED_TRANSITIONS).
const ALLOWED: Record<ApplicationStatus, ApplicationStatus[]> = {
  drafted: ["applied", "withdrawn"],
  applied: ["written_test", "interviewing", "rejected", "withdrawn", "offer_received"],
  written_test: ["interviewing", "rejected", "withdrawn", "offer_received"],
  interviewing: ["offer_received", "rejected", "withdrawn"],
  offer_received: [],
  rejected: [],
  withdrawn: [],
};
const SOURCE_OPTIONS = [
  { value: "", label: "不填" },
  { value: "内推", label: "内推" },
  { value: "招聘网站", label: "招聘网站" },
  { value: "官网", label: "官网" },
  { value: "其他", label: "其他" },
];

export default function TrackingPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [overview, setOverview] = useState<TrackingOverview | null>(null);
  const [apps, setApps] = useState<ApplicationOut[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Drawer state
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ApplicationOut | null>(null);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Pre-fill from Target Job (Phase 3 -> Phase 5 linkage, via URL query).
  const prefill = useMemo(() => {
    const company = params.get("company");
    const job = params.get("job");
    const city = params.get("city");
    const tjid = params.get("target_job_id");
    if (!company && !job) return null;
    return {
      company: company ?? "",
      job_title: job ?? "",
      city: city || null,
      target_job_id: tjid ? Number(tjid) : null,
    };
  }, [params]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, list] = await Promise.all([
        api.getTrackingOverview(),
        api.listApplications(statusFilter || undefined),
      ]);
      setOverview(ov);
      setApps(list.items);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, toast]);

  useEffect(() => {
    load();
  }, [load]);

  // If arriving from a Target Job with prefill params, open the editor.
  useEffect(() => {
    if (prefill && !editorOpen && !editing) {
      setEditing(null);
      setEditorOpen(true);
    }
  }, [prefill, editorOpen, editing]);

  const openCreate = () => {
    setEditing(null);
    setEditorOpen(true);
  };
  const openEdit = (app: ApplicationOut) => {
    setEditing(app);
    setEditorOpen(true);
  };
  const openDetail = async (app: ApplicationOut) => {
    setBusy(true);
    try {
      const d = await api.getApplication(app.application_id);
      setDetail(d);
      setDetailOpen(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载详情失败");
    } finally {
      setBusy(false);
    }
  };
  const closeEditor = () => {
    setEditorOpen(false);
    setEditing(null);
    // Clear prefill query params so a refresh doesn't re-open the drawer.
    if (params.get("company") || params.get("job")) {
      params.delete("company");
      params.delete("job");
      params.delete("city");
      params.delete("target_job_id");
      setParams(params, { replace: true });
    }
  };

  const [delApp, setDelApp] = useState<ApplicationOut | null>(null);
  const removeApp = (app: ApplicationOut) => setDelApp(app);

  const confirmRemoveApp = async () => {
    if (!delApp) return;
    setBusy(true);
    try {
      await api.deleteApplication(delApp.application_id);
      toast.success("已删除");
      await load();
      setDelApp(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tk">
      <header className="tk-head">
        <div>
          <h1 className="page-title">求职追踪</h1>
          <p className="page-desc">轻量记录投递与面试进度：公司、岗位、状态、面试轮次与结果。</p>
        </div>
        <Button variant="primary" icon="plus" onClick={openCreate}>记录投递</Button>
      </header>

      {loading ? (
        <LoadingState skeleton lines={4} />
      ) : (
        <>
          {/* Overview —— 统计卡本身就是状态筛选器（不再另设下拉框） */}
          {overview && (
            <section className="tk-overview" role="group" aria-label="按投递状态筛选">
              <button
                type="button"
                className={`tk-stat tk-stat--total ${statusFilter === "" ? "is-active" : ""}`}
                aria-pressed={statusFilter === ""}
                onClick={() => setStatusFilter("")}
              >
                <span className="tk-stat__num">{overview.total}</span>
                <span className="tk-stat__label">总投递</span>
              </button>
              {Object.entries(overview.counts_labeled).map(([label, n]) => {
                const status = LABEL_TO_STATUS[label];
                const active = status !== undefined && statusFilter === status;
                return (
                  <button
                    key={label}
                    type="button"
                    className={`tk-stat ${active ? "is-active" : ""}`}
                    aria-pressed={active}
                    onClick={() => {
                      if (status) setStatusFilter(status);
                    }}
                  >
                    <span className="tk-stat__num">{n}</span>
                    <span className="tk-stat__label">{label}</span>
                  </button>
                );
              })}
            </section>
          )}

          {/* Upcoming interviews */}
          {overview && overview.upcoming_interviews.length > 0 && (
            <section className="tk-upcoming">
              <h2 className="tk-section__title"><Icon name="calendar" size={16} /> 即将到来的面试</h2>
              <div className="tk-upcoming__list">
                {overview.upcoming_interviews.map((iv) => (
                  <button
                    key={iv.interview_id}
                    className="tk-upcoming__item"
                    onClick={() => {
                      const owner = apps.find((a) => a.application_id === iv.application_id);
                      if (owner) openDetail(owner);
                    }}
                  >
                    <span className="tk-upcoming__when">
                      {iv.scheduled_at ? new Date(iv.scheduled_at).toLocaleString("zh-CN") : "时间待定"}
                    </span>
                    <span className="tk-upcoming__company">
                      {iv.round ? `${iv.round} · ` : ""}{iv.interview_type || "面试"}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {/* List */}
          {apps.length === 0 ? (
            <EmptyState
              illustration={<IllustrationTracking />}
              icon="tracking"
              title="还没有投递记录"
              description="从目标岗位一键带入，或手动记录你投递的每一家公司。"
              action={<Button variant="primary" icon="plus" onClick={openCreate}>记录第一笔投递</Button>}
            />
          ) : (
            <div className="tk-list">
              {apps.map((a) => (
                <article key={a.application_id} className="tk-card">
                  <div className="tk-card__main">
                    <div className="tk-card__top">
                      <span className="tk-card__company">{a.company}</span>
                      <Tag tone={STATUS_TONE[a.status]}>{a.status_label}</Tag>
                    </div>
                    <div className="tk-card__job">{a.job_title}{a.city ? ` · ${a.city}` : ""}</div>
                    {a.next_action && (
                      <div className="tk-card__next"><Icon name="flag" size={13} /> {a.next_action}</div>
                    )}
                  </div>
                  <div className="tk-card__actions">
                    <Button variant="ghost" size="sm" icon="eye" onClick={() => openDetail(a)}>详情</Button>
                    <Button variant="ghost" size="sm" icon="edit" onClick={() => openEdit(a)}>编辑</Button>
                    <Button variant="ghost" size="sm" icon="trash" onClick={() => removeApp(a)}>删除</Button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}

      {/* Create / Edit drawer */}
      <Drawer open={editorOpen} onClose={closeEditor} title={editing ? "编辑投递记录" : "记录投递"}>
        <ApplicationEditor
          editing={editing}
          prefill={prefill}
          busy={busy}
          onDone={async () => {
            closeEditor();
            await load();
          }}
          onError={(m) => toast.error(m)}
          setBusy={setBusy}
        />
      </Drawer>

      {/* Detail drawer */}
      <Drawer open={detailOpen} onClose={() => setDetailOpen(false)} title="投递详情">
        {detail && (
          <ApplicationDetailView
            detail={detail}
            busy={busy}
            setBusy={setBusy}
            onReload={load}
            onError={(m) => toast.error(m)}
            onSuccess={(m) => toast.success(m)}
            onAddToOffer={(appId) => {
              const owner = apps.find((a) => a.application_id === appId)!;
              const q = new URLSearchParams();
              q.set("company", owner.company);
              q.set("job_title", owner.job_title);
              if (owner.city) q.set("city", owner.city);
              q.set("application_id", String(owner.application_id));
              if (owner.target_job_id) q.set("target_job_id", String(owner.target_job_id));
              setDetailOpen(false);
              navigate(`/offer?${q.toString()}`);
            }}
          />
        )}
      </Drawer>

      {/* 下一步：去 Offer 决策 */}
      <section className="next-step">
        <div className="next-step__text">
          <div className="next-step__title">下一步：去 Offer 决策</div>
          <div className="next-step__desc">把进入 offer_received 的投递，做成多维度 Offer 对比</div>
        </div>
        <div className="next-step__actions">
          <Button variant="primary" icon="arrowRight" onClick={() => navigate("/offer")}>
            去 Offer 决策
          </Button>
        </div>
      </section>

      <ConfirmDialog
        open={delApp !== null}
        title="删除投递记录"
        description={delApp ? `确认删除「${delApp.company} - ${delApp.job_title}」的投递记录？此操作不可恢复。` : ""}
        confirmText="删除"
        danger
        loading={busy}
        onConfirm={confirmRemoveApp}
        onClose={() => setDelApp(null)}
      />
    </div>
  );
}

// ----------------------------- editor -----------------------------
function ApplicationEditor({
  editing, prefill, busy, onDone, onError, setBusy,
}: {
  editing: ApplicationOut | null;
  prefill: { company: string; job_title: string; city: string | null; target_job_id: number | null } | null;
  busy: boolean;
  onDone: () => void;
  onError: (m: string) => void;
  setBusy: (b: boolean) => void;
}) {
  const initialCompany = editing?.company ?? prefill?.company ?? "";
  const initialJob = editing?.job_title ?? prefill?.job_title ?? "";
  const initialCity = editing?.city ?? prefill?.city ?? "";
  const initialTjid = editing?.target_job_id ?? prefill?.target_job_id ?? null;

  const [company, setCompany] = useState(initialCompany);
  const [jobTitle, setJobTitle] = useState(initialJob);
  const [city, setCity] = useState(initialCity ?? "");
  const [jobUrl, setJobUrl] = useState(editing?.job_url ?? "");
  const [source, setSource] = useState(editing?.source ?? "");
  const [appliedAt, setAppliedAt] = useState(editing?.applied_at ?? "");
  const [status, setStatus] = useState<ApplicationStatus>(editing?.status ?? "drafted");
  const [nextAction, setNextAction] = useState(editing?.next_action ?? "");
  const [nextActionAt, setNextActionAt] = useState(editing?.next_action_at ?? "");
  const [note, setNote] = useState(editing?.note ?? "");
  const [targetJobId] = useState<number | null>(initialTjid);

  const submit = async () => {
    if (!company.trim() || !jobTitle.trim()) {
      onError("公司名称与岗位名称均必填");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        company: company.trim(),
        job_title: jobTitle.trim(),
        city: city.trim() || null,
        job_url: jobUrl.trim() || null,
        source: source || null,
        applied_at: appliedAt || null,
        status,
        next_action: nextAction.trim() || null,
        next_action_at: nextActionAt || null,
        note: note || "",
        target_job_id: targetJobId,
      };
      if (editing) {
        await api.updateApplication(editing.application_id, payload);
      } else {
        await api.createApplication(payload);
      }
      onDone();
    } catch (e) {
      onError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tk-form">
      <Input label="公司名称 *" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="如：字节跳动" />
      <Input label="岗位名称 *" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="如：后端开发工程师" />
      <div className="tk-form__row">
        <Input label="城市" value={city} onChange={(e) => setCity(e.target.value)} placeholder="如：上海" />
        <Input label="投递链接" value={jobUrl} onChange={(e) => setJobUrl(e.target.value)} placeholder="招聘页 URL（选填）" />
      </div>
      <div className="tk-form__row">
        <Input label="投递日期" type="date" value={appliedAt ? appliedAt.slice(0, 10) : ""} onChange={(e) => setAppliedAt(e.target.value)} />
        <Select label="来源渠道" value={source} options={SOURCE_OPTIONS} onChange={(e) => setSource(e.target.value)} />
      </div>
      <Select
        label="状态"
        value={status}
        options={(Object.keys(STATUS_LABELS) as ApplicationStatus[]).map((s) => ({ value: s, label: STATUS_LABELS[s] }))}
        onChange={(e) => setStatus(e.target.value as ApplicationStatus)}
      />
      <div className="tk-form__row">
        <Input label="下一步动作" value={nextAction} onChange={(e) => setNextAction(e.target.value)} placeholder="如：等 HR 二面通知" />
        <Input label="下一步时间" type="date" value={nextActionAt ? nextActionAt.slice(0, 10) : ""} onChange={(e) => setNextActionAt(e.target.value)} />
      </div>
      <Textarea label="备注" value={note} onChange={(e) => setNote(e.target.value)} placeholder="自由记录（选填）" rows={3} />
      <div className="actions">
        <Button variant="ghost" onClick={onDone}>取消</Button>
        <Button variant="primary" loading={busy} icon="check" onClick={submit}>
          {editing ? "保存修改" : "保存投递"}
        </Button>
      </div>
    </div>
  );
}

// ----------------------------- detail view -----------------------------
function ApplicationDetailView({
  detail, busy, setBusy, onReload, onError, onSuccess, onAddToOffer,
}: {
  detail: ApplicationDetail;
  busy: boolean;
  setBusy: (b: boolean) => void;
  onReload: () => void;
  onError: (m: string) => void;
  onSuccess: (m: string) => void;
  onAddToOffer: (applicationId: number) => void;
}) {
  const app = detail.application;
  const [interviews, setInterviews] = useState<InterviewOut[]>(detail.interviews);
  const [ivDrawer, setIvDrawer] = useState(false);

  const refresh = async () => {
    try {
      const d = await api.getApplication(app.application_id);
      setInterviews(d.interviews);
      onReload();
    } catch (e) {
      onError(e instanceof Error ? e.message : "刷新失败");
    }
  };

  const changeStatus = async (next: ApplicationStatus) => {
    setBusy(true);
    try {
      await api.updateApplication(app.application_id, { status: next });
      onSuccess(`状态已更新为「${STATUS_LABELS[next]}」`);
      await refresh();
    } catch (e) {
      onError(e instanceof Error ? e.message : "状态更新失败");
    } finally {
      setBusy(false);
    }
  };

  const nextOptions = ALLOWED[app.status] ?? [];
  const [delIv, setDelIv] = useState<InterviewOut | null>(null);
  const removeIv = (iv: InterviewOut) => setDelIv(iv);

  const confirmRemoveIv = async () => {
    if (!delIv) return;
    setBusy(true);
    try {
      await api.deleteInterview(delIv.interview_id);
      setDelIv(null);
      await refresh();
    } catch (e) {
      onError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tk-detail">
      <div className="tk-detail__head">
        <div>
          <div className="tk-detail__company">{app.company}</div>
          <div className="muted">{app.job_title}{app.city ? ` · ${app.city}` : ""}</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Tag tone={STATUS_TONE[app.status]}>{app.status_label}</Tag>
          <Button size="sm" variant="secondary" icon="offer" onClick={() => onAddToOffer(app.application_id)}>
            加入 Offer 决策
          </Button>
        </div>
      </div>

      {/* Status transition */}
      <div className="tk-detail__status">
        <span className="field-label">推进状态</span>
        <div className="tk-detail__transitions">
          {nextOptions.length === 0 ? (
            <span className="muted">当前为终态，无法再变更</span>
          ) : (
            nextOptions.map((s) => (
              <Button key={s} size="sm" variant="secondary" loading={busy} onClick={() => changeStatus(s)}>
                → {STATUS_LABELS[s]}
              </Button>
            ))
          )}
        </div>
      </div>

      {/* Interviews */}
      <section className="tk-detail__section">
        <div className="tk-detail__sect-head">
          <h3 className="tk-section__title">面试记录</h3>
          <Button size="sm" variant="ghost" icon="plus" onClick={() => setIvDrawer(true)}>添加面试</Button>
        </div>
        {interviews.length === 0 ? (
          <p className="muted">还没有面试记录。</p>
        ) : (
          <div className="tk-iv-list">
            {interviews.map((iv) => (
              <div key={iv.interview_id} className="tk-iv">
                <div className="tk-iv__top">
                  <span>{iv.round || "面试"}{iv.interview_type ? ` · ${iv.interview_type}` : ""}</span>
                  <Tag tone={iv.result === "pass" ? "green" : iv.result === "fail" ? "red" : "gray"}>
                    {iv.result === "pass" ? "通过" : iv.result === "fail" ? "未通过" : "待定"}
                  </Tag>
                </div>
                {iv.scheduled_at && <div className="muted">{new Date(iv.scheduled_at).toLocaleString("zh-CN")}</div>}
                {iv.note && <p className="tk-iv__note">{iv.note}</p>}
                <button className="tk-iv__del" onClick={() => removeIv(iv)}>删除</button>
              </div>
            ))}
          </div>
        )}
      </section>

      <ConfirmDialog
        open={delIv !== null}
        title="删除面试记录"
        description={delIv ? `确认删除「${delIv.round || "面试"}${delIv.interview_type ? ` · ${delIv.interview_type}` : ""}」这条记录？` : ""}
        confirmText="删除"
        danger
        loading={busy}
        onConfirm={confirmRemoveIv}
        onClose={() => setDelIv(null)}
      />

      {/* Timeline (merged: status + interview events) */}
      <section className="tk-detail__section">
        <h3 className="tk-section__title">时间线</h3>
        <ul className="tk-timeline">
          {detail.timeline.map((ev, i) => (
            <li key={i} className={`tk-tl tk-tl--${ev.kind}`}>
              <span className="tk-tl__dot" />
              <div className="tk-tl__body">
                <div className="tk-tl__title">
                  {ev.kind === "status"
                    ? `状态：${STATUS_LABELS[(ev.status as ApplicationStatus) ?? "drafted"] ?? ev.status}`
                    : `面试：${ev.round || "面试"}${ev.interview_type ? ` · ${ev.interview_type}` : ""}`}
                </div>
                <div className="muted">{new Date(ev.ts).toLocaleString("zh-CN")}</div>
                {ev.note && <p className="tk-tl__note">{ev.note}</p>}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <Drawer open={ivDrawer} onClose={() => setIvDrawer(false)} title="添加面试">
        <InterviewEditor
          applicationId={app.application_id}
          busy={busy}
          setBusy={setBusy}
          onDone={async () => {
            setIvDrawer(false);
            await refresh();
          }}
          onError={onError}
        />
      </Drawer>
    </div>
  );
}

// ----------------------------- interview editor -----------------------------
function InterviewEditor({
  applicationId, busy, setBusy, onDone, onError,
}: {
  applicationId: number;
  busy: boolean;
  setBusy: (b: boolean) => void;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const [round, setRound] = useState("");
  const [type, setType] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [interviewer, setInterviewer] = useState("");
  const [note, setNote] = useState("");

  const submit = async () => {
    setBusy(true);
    try {
      // Convert local datetime-local to ISO with Z for the backend.
      const iso = scheduledAt ? new Date(scheduledAt).toISOString() : null;
      await api.createInterview(applicationId, {
        round: round.trim() || null,
        interview_type: type.trim() || null,
        scheduled_at: iso,
        interviewer: interviewer.trim() || null,
        note: note.trim() || null,
        status: "scheduled",
        result: "pending",
      });
      onDone();
    } catch (e) {
      onError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tk-form">
      <div className="tk-form__row">
        <Input label="轮次" value={round} onChange={(e) => setRound(e.target.value)} placeholder="如：一面 / HR面" />
        <Input label="类型" value={type} onChange={(e) => setType(e.target.value)} placeholder="如：技术 / 主管" />
      </div>
      <div className="tk-form__row">
        <Input label="时间" type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
        <Input label="面试官" value={interviewer} onChange={(e) => setInterviewer(e.target.value)} placeholder="选填" />
      </div>
      <Textarea label="备注" value={note} onChange={(e) => setNote(e.target.value)} placeholder="问题 / 感受 / 待改进（选填）" rows={3} />
      <div className="actions">
        <Button variant="ghost" onClick={onDone}>取消</Button>
        <Button variant="primary" loading={busy} icon="check" onClick={submit}>保存面试</Button>
      </div>
    </div>
  );
}
