import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { ChangeEvent } from "react";
import { api } from "../../api/client";
import type {
  OfferOut,
  OfferIn,
  CityCost,
  OfferDimensionView,
  SalaryResult,
  ComparisonResult,
  ApplicationOut,
} from "../../api/client";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Drawer from "../../components/ui/Drawer";
import Input from "../../components/ui/Input";
import Select from "../../components/ui/Select";
import Tag from "../../components/ui/Tag";
import { useToast } from "../../components/ui/Toast";
import EmptyState from "../../components/ui/EmptyState";
import LoadingState from "../../components/ui/LoadingState";
import ConfirmDialog from "../../components/ui/ConfirmDialog";
import { IllustrationOffer } from "../../components/ui/Illustrations";
import AiBadge from "../../components/AiBadge";

/* 状态色按语义映射（全站降噪）：
   accepted「已接受」是**正向状态** → 绿；draft/active/rejected/expired 都是中性事实 → 灰。
   旧值把 accepted 映射成 red（红色在本站语义是删除/错误/风险），
   等于把"已拿 Offer"标成了告警色，且与 active 的蓝色互相打架。 */
const STATUS_COLORS: Record<string, "blue" | "green" | "orange" | "red" | "gray"> = {
  draft: "gray",
  active: "gray",
  accepted: "green",
  rejected: "gray",
  expired: "gray",
};

const DIM_LABELS: Record<string, string> = {
  economic: "经济收益",
  disposable: "可支配收入",
  workload: "工作强度",
  stability: "稳定性",
  growth: "发展空间",
  match: "岗位匹配度",
};

// F22 决策偏好预设（与后端 decision_service.PRESETS 一致；仅 UI 接线，不新增 API）。
const WEIGHT_PRESETS: Record<string, { label: string; weights: Record<string, number> }> = {
  balanced: { label: "均衡方案", weights: { economic: 25, disposable: 20, workload: 15, stability: 15, growth: 15, match: 10 } },
  salary: { label: "薪资优先", weights: { economic: 40, disposable: 30, workload: 10, stability: 5, growth: 10, match: 5 } },
  stability: { label: "稳定优先", weights: { economic: 15, disposable: 10, workload: 15, stability: 35, growth: 15, match: 10 } },
  growth: { label: "发展优先", weights: { economic: 15, disposable: 10, workload: 10, stability: 10, growth: 40, match: 15 } },
};
const DIM_ORDER = ["economic", "disposable", "workload", "stability", "growth", "match"];

export default function OfferPage() {
  const [params, setParams] = useSearchParams();
  const presetPrefill = {
    company: params.get("company") || "",
    job_title: params.get("job_title") || "",
    city: params.get("city") || "",
    application_id: params.get("application_id") ? Number(params.get("application_id")) : null,
    target_job_id: params.get("target_job_id") ? Number(params.get("target_job_id")) : null,
  };

  const [offers, setOffers] = useState<OfferOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<OfferOut | null>(null);
  const [creating, setCreating] = useState(false);
  // Phase 6.5-5.1: prefill override picked from an existing Application.
  const [prefillOverride, setPrefillOverride] = useState<typeof presetPrefill | null>(null);
  const [appPickerOpen, setAppPickerOpen] = useState(false);
  const [apps, setApps] = useState<ApplicationOut[]>([]);
  // Phase 6.5-5.2: F22 decision weights.
  const [weights, setWeights] = useState<Record<string, number> | null>(null);
  const [presetName, setPresetName] = useState<string | null>(null);
  const [detail, setDetail] = useState<OfferOut | null>(null);
  const [calcDrawer, setCalcDrawer] = useState<OfferOut | null>(null);
  const [cities, setCities] = useState<CityCost[]>([]);
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [compareBusy, setCompareBusy] = useState(false);
  const [delOffer, setDelOffer] = useState<OfferOut | null>(null);
  // 综合得分 / 排名（由已有 getComparison 端点计算，仅用于卡片视觉突出，不改评分逻辑）。
  const [scores, setScores] = useState<Record<number, { composite_score: number; rank: number }>>({});
  /* ★ 决策偏好(权重)的"已落库版本号"。
     根因（线上验收："改了决策偏好，综合分没变"）：
     分数的 useEffect 依赖数组里**只有 offers**，所以加载完 Offer 之后
     再也不会重新拉取 comparison —— 用户改了偏好、权重也存进后端了，
     但页面上那张分数表还是首次挂载时那一次的结果。
     修法：权重**成功落库后**把版本号 +1，让同一条 effect 再跑一次。
     强调"成功落库后"——综合分必须由程序按**已持久化的权重**重算，
     不能在客户端本地推算（那等于把评分逻辑复制一份到前端）。 */
  const [weightsRev, setWeightsRev] = useState(0);
  const toast = useToast();
  const navigate = useNavigate();

  const loadOffers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listOffers();
      setOffers(res.items);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCities = useCallback(async () => {
    try {
      const c = await api.listCities();
      setCities(c.cities);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadOffers();
    loadCities();
  }, [loadOffers, loadCities]);

  // Phase 6.5-5.2: load F22 weights on mount.
  useEffect(() => {
    api
      .getWeights()
      .then((w) => { setWeights(w.weights); setPresetName(w.preset_name); })
      .catch(() => { /* keep null -> panel shows defaults */ });
  }, []);

  // 自动拉取各 Offer 综合得分 / 排名，让比较结果成为首屏焦点（不改评分逻辑）。
  // 依赖里必须带 weightsRev：偏好一改，程序就要用新权重重算一遍。
  useEffect(() => {
    if (offers.length === 0) return;
    let cancelled = false;
    api
      .getComparison(offers.map((o) => o.offer_id))
      .then((c) => {
        if (cancelled) return;
        const map: Record<number, { composite_score: number; rank: number }> = {};
        c.offers.forEach((o) => {
          map[o.offer_id] = { composite_score: o.composite_score, rank: o.rank };
        });
        setScores(map);
      })
      .catch(() => { /* 分数为可选展示，失败不影响列表 */ });
    return () => { cancelled = true; };
  }, [offers, weightsRev]);

  // Phase 6.5-5.1: open the "from applications" picker (lists existing tracking records).
  const openAppPicker = async () => {
    setAppPickerOpen(true);
    try {
      const r = await api.listApplications();
      setApps(r.items);
    } catch {
      setApps([]);
    }
  };

  const startFromApp = (a: ApplicationOut) => {
    setAppPickerOpen(false);
    setEditing(null);
    setPrefillOverride({
      company: a.company,
      job_title: a.job_title,
      city: a.city ?? "",
      application_id: a.application_id,
      target_job_id: a.target_job_id,
    });
    setCreating(true);
  };

  // Phase 6.5-5.2: apply a preset (F22, user-confirmed action -> saved).
  // 保存成功后再 bump weightsRev —— 顺序不能反：先落库、再重算，
  // 否则重新拉取的 comparison 读到的还是旧权重，页面会"改了但没变"。
  const applyPreset = async (key: string) => {
    const preset = WEIGHT_PRESETS[key];
    if (!preset) return;
    setWeights(preset.weights);
    setPresetName(key);
    try {
      await api.saveWeights({ weights: preset.weights, preset_name: key });
      setWeightsRev((v) => v + 1);
      toast.success(`已应用「${preset.label}」，综合得分已按新权重重算`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "应用方案失败");
    }
  };

  const saveCustomWeights = async () => {
    if (!weights) return;
    try {
      await api.saveWeights({ weights, preset_name: null });
      setPresetName(null);
      setWeightsRev((v) => v + 1); // 同上：落库成功后才重算
      toast.success("权重已保存，综合得分已按新权重重算");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    }
  };

  // Auto-open creation drawer when arriving via Tracking prefill (mount-only).
  useEffect(() => {
    if (presetPrefill.company || presetPrefill.job_title) {
      setCreating(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshComparison = useCallback(async (ids?: number[]) => {
    const res = await api.getComparison(ids);
    return res;
  }, []);

  const toggleSelect = (id: number) => {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-3)));
  };

  return (
    <div className="tk">
      <div className="tk-head">
        <div>
          <h1 className="page-title">Offer 决策</h1>
          <p className="page-desc">把不同 Offer 放在同一张桌子上，看清真正的差异。</p>
        </div>
        <div className="tk-head__actions">
          <Button variant="secondary" icon="tracking" onClick={openAppPicker}>从已投递添加</Button>
          <Button variant="primary" icon="plus" onClick={() => { setEditing(null); setPrefillOverride(null); setCreating(true); }}>
            添加 Offer
          </Button>
        </div>
      </div>

      {loading ? (
        <LoadingState skeleton lines={4} />
      ) : offers.length === 0 ? (
        <EmptyState
          illustration={<IllustrationOffer />}
          title="还没有任何 Offer"
          description="添加你的第一个 Offer，开始对比税后收入、生活成本与多维评估。"
          action={<Button variant="primary" icon="plus" onClick={() => { setEditing(null); setCreating(true); }}>添加 Offer</Button>}
        />
      ) : (
        <>
          <div className="tk-compare-intro">
            你正在比较 {offers.length} 个 Offer · 综合得分由程序按你的权重计算
          </div>
          <div className="tk-filter">
            <Button
              variant={compareMode ? "primary" : "secondary"}
              icon="compare"
              onClick={() => { setCompareMode((v) => !v); setSelected([]); }}
            >
              {compareMode ? "退出比较" : "比较 Offer"}
            </Button>
          </div>
          <div className="tk-list">
            {offers.map((o) => {
              const s = scores[o.offer_id];
              return (
              <Card key={o.offer_id} className="tk-card">
                <div className="tk-card__top">
                  <div>
                    <div className="tk-card__company">{o.company}</div>
                    <div className="tk-card__job">{o.job_title}{o.city ? ` · ${o.city}` : ""}</div>
                  </div>
                  {s && (
                    <div className="tk-card__score">
                      <div className="tk-card__score-num">{s.composite_score}</div>
                      <div className="tk-card__score-label">综合得分</div>
                    </div>
                  )}
                  <Tag tone={STATUS_COLORS[o.status] || "gray"}>{o.status_label}</Tag>
                  {s && <Tag tone="gray">第 {s.rank} 名</Tag>}
                </div>
                <div className="tk-card__actions">
                  {compareMode && (
                    <Button variant="secondary" onClick={() => toggleSelect(o.offer_id)}>
                      {selected.includes(o.offer_id) ? "已选" : "选择"}
                    </Button>
                  )}
                  <Button variant="ghost" icon="eye" onClick={() => setDetail(o)}>查看</Button>
                  <Button variant="ghost" icon="edit" onClick={() => { setEditing(o); setCreating(true); }}>编辑</Button>
                  <Button variant="ghost" icon="trash" onClick={() => setDelOffer(o)}>
                    删除
                  </Button>
                </div>
              </Card>
              );
            })}
          </div>

          {compareMode && selected.length >= 2 && (
            <div className="tk-compare-bar">
              <span>已选 {selected.length} 个 Offer</span>
              <Button
                variant="primary"
                loading={compareBusy}
                onClick={async () => {
                  setCompareBusy(true);
                  try {
                    const cmp = await refreshComparison(selected);
                    setComparison(cmp);
                  } catch (e) {
                    toast.error(e instanceof Error ? e.message : "对比加载失败");
                  } finally {
                    setCompareBusy(false);
                  }
                }}
              >
                比较这 {selected.length} 个
              </Button>
            </div>
          )}
        </>
      )}

      {/* 决策偏好降级为次级 Section：默认折叠，放在比较结果之后 */}
      {weights && (
        <details className="tk-weights-collapsible">
          <summary className="tk-weights-collapsible__summary">
            调整你的决策偏好（影响综合排序，但不替你做决定）
          </summary>
          <WeightsPanel
            weights={weights}
            presetName={presetName}
            onPreset={applyPreset}
            onChange={setWeights}
            onSave={saveCustomWeights}
          />
        </details>
      )}

      {creating && (
        <OfferForm
          initial={editing}
          cities={cities}
          prefill={prefillOverride ?? presetPrefill}
          onClose={() => { setCreating(false); setEditing(null); setPrefillOverride(null); setParams({}); }}
          onSaved={() => { setCreating(false); setEditing(null); setPrefillOverride(null); setParams({}); loadOffers(); }}
        />
      )}

      {/* Phase 6.5-5.1: 从已投递记录添加 Offer（用户主动选择才进入创建流程） */}
      {appPickerOpen && (
        <AppPickerDrawer
          apps={apps}
          onPick={startFromApp}
          onClose={() => setAppPickerOpen(false)}
        />
      )}

      {detail && (
        <OfferDetail
          offer={detail}
          onClose={() => setDetail(null)}
          onAccept={async () => {
            try {
              const r = await api.acceptOffer(detail.offer_id);
              toast.success(r.hint || "已标记为接受");
              loadOffers();
              setDetail(null);
            } catch (e) {
              toast.error(e instanceof Error ? e.message : "操作失败");
            }
          }}
          onOpenCalc={() => setCalcDrawer(detail)}
        />
      )}

      {calcDrawer && (
        <SalaryDrawer offer={calcDrawer} onClose={() => setCalcDrawer(null)} />
      )}

      {comparison && (
        <ComparisonModal
          comparison={comparison}
          onClose={() => setComparison(null)}
          onAdjustWeights={() => setComparison(null)}
        />
      )}

      <ConfirmDialog
        open={delOffer !== null}
        title="删除 Offer"
        description={delOffer ? `确认删除「${delOffer.company} · ${delOffer.job_title}」？此操作不可恢复。` : ""}
        confirmText="删除"
        danger
        onConfirm={async () => {
          if (!delOffer) return;
          try {
            await api.deleteOffer(delOffer.offer_id);
            toast.success("已删除");
            setDelOffer(null);
            loadOffers();
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "删除失败");
          }
        }}
        onClose={() => setDelOffer(null)}
      />

      {/* 下一步：回到职业画像，开启新一轮探索 */}
      <section className="next-step">
        <div className="next-step__text">
          <div className="next-step__title">决策完成？回到职业画像</div>
          <div className="next-step__desc">重新审视你的定位与方向，开启下一轮更精准的探索</div>
        </div>
        <div className="next-step__actions">
          <Button variant="primary" icon="arrowRight" onClick={() => navigate("/profile")}>
            回到职业画像
          </Button>
        </div>
      </section>
    </div>
  );
}

function OfferForm({ initial, cities, prefill, onClose, onSaved }: {
  initial: OfferOut | null;
  cities: CityCost[];
  prefill: Record<string, unknown>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [company, setCompany] = useState(initial?.company ?? (prefill.company as string) ?? "");
  const [jobTitle, setJobTitle] = useState(initial?.job_title ?? (prefill.job_title as string) ?? "");
  const [city, setCity] = useState(initial?.city ?? (prefill.city as string) ?? "");
  const [industry, setIndustry] = useState(initial?.industry ?? "");
  const [monthlyBase, setMonthlyBase] = useState(initial?.salary?.monthly_base ?? 0);
  const [bonusMonths, setBonusMonths] = useState(initial?.salary?.annual_bonus_months ?? 0);
  const [signOn, setSignOn] = useState(initial?.salary?.sign_on ?? 0);
  const [equity, setEquity] = useState(initial?.salary?.equity_value ?? 0);
  const [special, setSpecial] = useState(initial?.special_deduction ?? 0);
  const [fundRate, setFundRate] = useState(initial?.fund_rate ?? "");
  const [status, setStatus] = useState(initial?.status ?? "draft");

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const input: OfferIn = {
        company, job_title: jobTitle, city: city || null, industry: industry || null,
        salary: {
          monthly_base: Number(monthlyBase) || 0,
          annual_bonus_months: Number(bonusMonths) || 0,
          sign_on: Number(signOn) || 0,
          equity_value: Number(equity) || 0,
        },
        special_deduction: Number(special) || 0,
        fund_rate: fundRate === "" ? null : Number(fundRate),
        status,
        application_id: (prefill.application_id as number) ?? initial?.application_id ?? null,
        target_job_id: (prefill.target_job_id as number) ?? initial?.target_job_id ?? null,
      };
      if (initial) {
        await api.updateOffer(initial.offer_id, input);
      } else {
        await api.createOffer(input);
      }
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer open title={initial ? "编辑 Offer" : "添加 Offer"} onClose={onClose}>
      <div className="tk-form">
        {error && <div className="notice notice--error">{error}</div>}
        <Input label="公司名称" value={company} onChange={(e: ChangeEvent<HTMLInputElement>) => setCompany(e.target.value)} placeholder="如 字节跳动" />
        <Input label="岗位名称" value={jobTitle} onChange={(e: ChangeEvent<HTMLInputElement>) => setJobTitle(e.target.value)} placeholder="如 后端开发" />
        <div className="tk-form__row">
          <Select label="城市" value={city} onChange={(e: ChangeEvent<HTMLSelectElement>) => setCity(e.target.value)} options={[
            { value: "", label: "未填写" }, ...cities.map((c) => ({ value: c.city, label: c.city })),
          ]} />
          <Input label="行业" value={industry} onChange={(e: ChangeEvent<HTMLInputElement>) => setIndustry(e.target.value)} placeholder="如 互联网" />
        </div>
        <Input label="税前月薪 (元)" value={String(monthlyBase)} onChange={(e: ChangeEvent<HTMLInputElement>) => setMonthlyBase(Number(e.target.value) || 0)} type="number" />
        <div className="tk-form__row">
          <Input label="年终奖 (月)" value={String(bonusMonths)} onChange={(e: ChangeEvent<HTMLInputElement>) => setBonusMonths(Number(e.target.value) || 0)} type="number" />
          <Input label="公积金比例 (默认城市)" value={fundRate} onChange={(e: ChangeEvent<HTMLInputElement>) => setFundRate(e.target.value)} placeholder="如 0.12" />
        </div>
        <div className="tk-form__row">
          <Input label="签字费 (元)" value={String(signOn)} onChange={(e: ChangeEvent<HTMLInputElement>) => setSignOn(Number(e.target.value) || 0)} type="number" />
          <Input label="股票/期权估值 (元)" value={String(equity)} onChange={(e: ChangeEvent<HTMLInputElement>) => setEquity(Number(e.target.value) || 0)} type="number" />
        </div>
        <Input label="专项附加扣除 (元/月)" value={String(special)} onChange={(e: ChangeEvent<HTMLInputElement>) => setSpecial(Number(e.target.value) || 0)} type="number" />
        <Select label="状态" value={status} onChange={(e: ChangeEvent<HTMLSelectElement>) => setStatus(e.target.value)} options={[
          { value: "draft", label: "草稿" }, { value: "active", label: "进行中" },
          { value: "rejected", label: "已放弃" }, { value: "expired", label: "已过期" },
        ]} />
        <div className="tk-form__actions">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button variant="primary" loading={busy} onClick={submit}>{busy ? "保存中…" : "保存"}</Button>
        </div>
      </div>
    </Drawer>
  );
}

function OfferDetail({ offer, onClose, onAccept, onOpenCalc }: {
  offer: OfferOut;
  onClose: () => void;
  onAccept: () => void;
  onOpenCalc: () => void;
}) {
  const [notes, setNotes] = useState("");
  const [assess, setAssess] = useState<Record<string, OfferDimensionView> | null>(null);
  const [assessStatus, setAssessStatus] = useState<"ok" | "fallback" | undefined>(undefined);
  const [cmp, setCmp] = useState<ComparisonResult | null>(null);
  const [assessBusy, setAssessBusy] = useState(false);
  const [cmpBusy, setCmpBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const runAssess = async () => {
    if (assessBusy) return;
    setAssessBusy(true);
    setActionError(null);
    try {
      const r = await api.assessOffer(offer.offer_id, { user_notes: notes });
      setAssess(r.assessments);
      setAssessStatus(r.ai_status as "ok" | "fallback" | undefined);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "AI 评估失败");
    } finally {
      setAssessBusy(false);
    }
  };
  const runCmp = async () => {
    if (cmpBusy) return;
    setCmpBusy(true);
    setActionError(null);
    try {
      const r = await api.getComparison([offer.offer_id]);
      setCmp(r);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "综合评分计算失败");
    } finally {
      setCmpBusy(false);
    }
  };

  return (
    <Drawer open title={`${offer.company} · ${offer.job_title}`} onClose={onClose}>
      <div className="tk-detail__head">
        <div>
          <div className="tk-detail__company">{offer.company}</div>
          <div className="tk-card__job">{offer.job_title}{offer.city ? ` · ${offer.city}` : ""}</div>
        </div>
        <Tag tone={STATUS_COLORS[offer.status] || "gray"}>{offer.status_label}</Tag>
      </div>

      <div className="tk-detail__section">
        <div className="tk-section__title">经济部分</div>
        <Button variant="secondary" icon="calc" onClick={onOpenCalc}>查看税后收入计算</Button>
        <p className="tk-hint">估算结果，仅用于 Offer 横向比较。</p>
      </div>

      <div className="tk-detail__section">
        <div className="tk-section__head">
          <div className="tk-section__title">非经济因素 {assess && <AiBadge aiStatus={assessStatus} />}</div>
          <Button variant="ghost" onClick={runAssess} icon="sparkles" loading={assessBusy}>AI 评估</Button>
        </div>
        {actionError && <div className="notice notice--error" style={{ marginBottom: 10 }}>{actionError}</div>}
        <Input label="你的主观备注（最高优先级）" value={notes} onChange={(e: ChangeEvent<HTMLInputElement>) => setNotes(e.target.value)} placeholder="例如：加班较多但成长快" />
        <div className="tk-iv-list">
          {["workload", "stability", "growth", "match"].map((dim) => {
            const a = assess?.[dim];
            return (
              <div className="tk-iv" key={dim}>
                <div className="tk-iv__top"><span>{DIM_LABELS[dim]}</span><Tag tone="purple">{a?.tier || "未评估"}</Tag></div>
                <div className="tk-iv__note">{a?.reason || "点击「AI 评估」获取定性判断，或自行判断。"}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="tk-detail__section">
        <div className="tk-section__title">综合结果</div>
        <Button variant="secondary" onClick={runCmp} icon="compare" loading={cmpBusy}>计算综合评分</Button>
        {cmp && (
          <div className="tk-list">
            {cmp.offers.map((o) => (
              <div className="tk-card" key={o.offer_id}>
                <div>
                  <div className="tk-card__company">{o.company} · {o.job_title}</div>
                  <div className="tk-card__job">综合得分 {o.composite_score}</div>
                </div>
                <Tag tone="gray">第 {o.rank} 名</Tag>
              </div>
            ))}
            <div className="ai-block" style={{ marginTop: 12 }}>
            <div className="ai-block-header">
              <AiBadge aiStatus={cmp.analysis.ai_status as "ok" | "fallback"} />
            </div>
            {cmp.analysis.recommendations.map((r, i) => (
                <Card key={i} className="tk-card">
                  <div className="tk-iv__note">{r.focus}</div>
                  {r.conditionals.map((c, j) => <div className="tk-iv__note" key={j}>· {c}</div>)}
                  {r.caveats.map((c, j) => <div className="tk-iv__note" key={j}>⚠️ {c}</div>)}
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="tk-form__actions">
        <Button variant="ghost" onClick={onClose}>关闭</Button>
        {offer.status !== "accepted" && <Button variant="primary" onClick={onAccept}>标记为我的选择</Button>}
      </div>
    </Drawer>
  );
}

function ComparisonModal({ comparison, onClose, onAdjustWeights }: {
  comparison: ComparisonResult;
  onClose: () => void;
  onAdjustWeights: () => void;
}) {
  const offers = [...comparison.offers].sort((a, b) => a.rank - b.rank);
  const bestScore = offers.length ? Math.max(...offers.map((o) => o.composite_score ?? 0)) : 0;
  return (
    <div className="cmp-modal" role="dialog" aria-modal="true">
      <div className="cmp-modal__box">
        <div className="cmp-modal__head">
          <h2 className="cmp-modal__title">Offer 对比</h2>
          <button className="cmp-modal__close" onClick={onClose} aria-label="关闭">×</button>
        </div>

        <div className="cmp-table-wrap">
          <table className="cmp-table">
            <thead>
              <tr>
                <th className="cmp-table__label">维度</th>
                {offers.map((o) => (
                  <th key={o.offer_id} className="cmp-table__col">
                    <div className="cmp-table__title">{o.company}</div>
                    <div className="cmp-table__sub">{o.job_title}{o.city ? ` · ${o.city}` : ""}</div>
                    <Tag tone={o.rank === 1 ? "red" : "gray"}>第 {o.rank} 名</Tag>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="cmp-table__score-row">
                <td className="cmp-table__label">综合评分</td>
                {offers.map((o) => (
                  <td key={o.offer_id} className={`cmp-table__num cmp-table__score ${o.composite_score === bestScore ? "is-best" : ""}`}>
                    {o.composite_score ?? "—"}
                  </td>
                ))}
              </tr>
              {DIM_ORDER.map((dim) => (
                <tr key={dim}>
                  <td className="cmp-table__label">{DIM_LABELS[dim] ?? dim}</td>
                  {offers.map((o) => (
                    <td key={o.offer_id} className="cmp-table__num">
                      {o.dimension_scores?.[dim] ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
              <tr>
                <td className="cmp-table__label">城市生活成本</td>
                {offers.map((o) => {
                  const cc = o.city ? comparison.city_costs?.[o.city] : undefined;
                  return (
                    <td key={o.offer_id} className="cmp-table__num">
                      {cc ? `¥${cc.monthly_total}/月 · ¥${cc.annual_total}/年` : "—"}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>

        <div className="ai-block cmp-ai">
          <div className="ai-block-header">
            <AiBadge aiStatus={comparison.analysis.ai_status as "ok" | "fallback"} />
            <span className="cmp-ai__hint">解释而非决定</span>
          </div>
          {comparison.analysis.recommendations.map((r, i) => (
            <Card key={i} className="tk-card">
              <div className="tk-iv__note">{r.focus}</div>
              {r.conditionals.map((c, j) => <div className="tk-iv__note" key={j}>· {c}</div>)}
              {r.caveats.map((c, j) => <div className="tk-iv__note" key={j}>⚠️ {c}</div>)}
            </Card>
          ))}
        </div>

        <div className="cmp-modal__actions">
          <Button variant="secondary" icon="panel" onClick={onAdjustWeights}>调整我的决策偏好</Button>
          <Button variant="primary" onClick={onClose}>完成</Button>
        </div>
      </div>
    </div>
  );
}

// Phase 6.5-5.2/5.3: F22 权重面板 + 决策偏好建议（程序生成建议，不虚构 AI 数据）。
function WeightsPanel({ weights, presetName, onPreset, onChange, onSave }: {
  weights: Record<string, number>;
  presetName: string | null;
  onPreset: (key: string) => void;
  onChange: (w: Record<string, number>) => void;
  onSave: () => void;
}) {
  const top = DIM_ORDER.filter((d) => weights[d] !== undefined)
    .sort((a, b) => (weights[b] ?? 0) - (weights[a] ?? 0))[0];
  const active = presetName ? WEIGHT_PRESETS[presetName] ?? null : null;
  const advice = active
    ? `你当前采用「${active.label}」：${(active.weights.economic ?? 0) > (active.weights.stability ?? 0) ? "更偏向收入与成长" : "更偏向长期稳定"}。如果你更在意薪资，可考虑提高经济收益与可支配收入的权重；更在意长期确定性，则提高稳定性。最终权重由你决定。`
    : top
      ? `你当前最看重「${DIM_LABELS[top] ?? top}」（权重 ${weights[top]}）。如果你更在意薪资，可考虑提高经济收益权重；更在意长期确定性，则提高稳定性。最终权重由你决定。`
      : "调整权重或选择预设方案，让排序更贴近你在意的因素。";
  return (
    <section className="tk-weights">
      <div className="tk-weights__head">
        <div>
          <h2 className="tk-section__title">我的决策偏好</h2>
          <p className="tk-hint">
            这次选 Offer 你更看重什么？权重会影响综合排序，但不会替你做决定。
            选预设会立即按新权重重算；拖动滑块后请点「保存权重」。
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={onSave}>保存权重</Button>
      </div>
      <div className="tk-weights__body">
        <div className="tk-weights__sliders">
          {DIM_ORDER.map((dim) => (
            <label key={dim} className="tk-weight">
              <span className="tk-weight__label">{DIM_LABELS[dim] ?? dim}</span>
              <input
                type="range" min={0} max={100}
                value={weights[dim] ?? 0}
                onChange={(e) => onChange({ ...weights, [dim]: Number(e.target.value) })}
              />
              <span className="tk-weight__val">{weights[dim] ?? 0}</span>
            </label>
          ))}
        </div>
        <div className="tk-weights__presets">
          {Object.entries(WEIGHT_PRESETS).map(([key, p]) => (
            <button
              key={key}
              className={`tk-preset ${presetName === key ? "is-active" : ""}`}
              onClick={() => onPreset(key)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="tk-weights__advice">
          <span className="tk-weights__advice-label">✦ 决策偏好建议</span>
          <p>{advice}</p>
        </div>
      </div>
    </section>
  );
}

// Phase 6.5-5.1: 从已投递记录添加 Offer（用户主动选择 → 预填 → 确认后才创建）。
function AppPickerDrawer({ apps, onPick, onClose }: {
  apps: ApplicationOut[];
  onPick: (a: ApplicationOut) => void;
  onClose: () => void;
}) {
  return (
    <Drawer open title="从已投递记录添加 Offer" onClose={onClose}>
      {apps.length === 0 ? (
        <EmptyState icon="tracking" title="暂无投递记录" description="先在「求职追踪」记录投递，再到这边添加 Offer。" />
      ) : (
        <div className="tk-list">
          {apps.map((a) => (
            <div key={a.application_id} className="tk-card">
              <div>
                <div className="tk-card__company">{a.company}</div>
                <div className="tk-card__job">{a.job_title}{a.city ? ` · ${a.city}` : ""}</div>
              </div>
              <div className="tk-card__actions">
                <Tag tone={STATUS_COLORS[a.status] || "gray"}>{a.status_label}</Tag>
                <Button variant="primary" size="sm" icon="plus" onClick={() => onPick(a)}>添加</Button>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="tk-hint">只做预填，不会自动生成 Offer；确认保存后才会创建。</p>
    </Drawer>
  );
}

function SalaryDrawer({ offer, onClose }: {
  offer: OfferOut;
  onClose: () => void;
}) {
  const [result, setResult] = useState<SalaryResult | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [calcBusy, setCalcBusy] = useState(false);
  const [special, setSpecial] = useState(offer.special_deduction);
  const [fund, setFund] = useState(offer.fund_rate ?? "");
  const [monthly, setMonthly] = useState(offer.salary?.monthly_base ?? 0);
  const [bonus, setBonus] = useState(offer.salary?.annual_bonus_months ?? 0);

  const calc = async ({ overrideCity }: { overrideCity?: string } = {}) => {
    if (calcBusy) return;
    setCalcBusy(true);
    setCalcError(null);
    try {
      const r = await api.salaryCalc(offer.offer_id, {
        monthly_base: Number(monthly) || 0,
        annual_bonus_months: Number(bonus) || 0,
        special_deduction: Number(special) || 0,
        fund_rate: fund === "" ? null : Number(fund),
        city: overrideCity ?? offer.city,
      });
      setResult(r.results);
    } catch (e) {
      setCalcError(e instanceof Error ? e.message : "计算失败");
    } finally {
      setCalcBusy(false);
    }
  };
  // 仅首次打开时按 Offer 现值计算一次；后续由"重新计算"按钮显式触发
  useEffect(() => {
    calc();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Drawer open title="税后收入计算" onClose={onClose}>
      <div className="tk-form">
        <Input label="税前月薪" value={String(monthly)} onChange={(e: ChangeEvent<HTMLInputElement>) => setMonthly(Number(e.target.value) || 0)} type="number" />
        <div className="tk-form__row">
          <Input label="年终奖 (月)" value={String(bonus)} onChange={(e: ChangeEvent<HTMLInputElement>) => setBonus(Number(e.target.value) || 0)} type="number" />
          <Input label="公积金比例" value={fund} onChange={(e: ChangeEvent<HTMLInputElement>) => setFund(e.target.value)} placeholder="默认城市" />
        </div>
        <Input label="专项附加扣除 (元/月)" value={String(special)} onChange={(e: ChangeEvent<HTMLInputElement>) => setSpecial(Number(e.target.value) || 0)} type="number" />
        <div className="tk-hint">基于城市 {offer.city || "（未填）"} 的五险一金上下限与个税累进税率估算。</div>
        {calcError && <div className="notice notice--error">{calcError}</div>}
        {result && (
          <div className="tk-iv-list">
            <div className="tk-iv"><div className="tk-iv__top"><span>税前月薪</span><b>{result.monthly_base} 元</b></div></div>
            <div className="tk-iv"><div className="tk-iv__top"><span>五险一金 (个人)</span><b>-{result.insurance_total} 元/月</b></div></div>
            <div className="tk-iv"><div className="tk-iv__top"><span>个税</span><b>-{result.monthly_tax} 元/月</b></div></div>
            <div className="tk-iv"><div className="tk-iv__top"><span>税后月薪</span><b>{result.monthly_after_tax} 元</b></div></div>
            <div className="tk-iv"><div className="tk-iv__top"><span>年终奖税后</span><b>{result.annual_bonus_after_tax} 元</b></div></div>
            <div className="tk-iv"><div className="tk-iv__top"><span>预计年税后</span><b>{result.annual_after_tax} 元</b></div></div>
            <div className="tk-iv"><div className="tk-iv__top"><span>签字费 / 股票 (不计入核心)</span><b>{result.sign_on} / {result.equity_value} 元</b></div></div>
          </div>
        )}
        <div className="tk-form__actions">
          <Button variant="ghost" onClick={onClose}>关闭</Button>
          <Button variant="primary" loading={calcBusy} onClick={() => calc()}>重新计算</Button>
        </div>
      </div>
    </Drawer>
  );
}
