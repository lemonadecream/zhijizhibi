/**
 * Offer 决策偏好 → 综合分重算 链路回归。
 *
 * 线上验收发现的问题：页面写着「调整你的决策偏好（影响综合排序，但不替你做决定）」，
 * 但实操改了偏好之后，卡片上的综合得分一动不动。
 *
 * 排查结论：后端是好的（PUT /api/offer/weights 落库 → GET /api/offer/comparison
 * 经 compute_comparison → get_weights 读到新权重）。断点在前端 ——
 * 拉分数的 useEffect 依赖数组里**只有 offers**，权重保存后根本不会再拉一次。
 *
 * 本文件锁住修复后的契约，共三条：
 *   1. 权重保存成功后，必须重新拉取 comparison；
 *   2. 顺序必须是"先落库、再重算"（否则拉到的还是旧权重）；
 *   3. 重新拉取拿到的分数必须真的被渲染出来（不只是请求发了）。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ComparisonResult, OfferOut } from "../api/client";
import OfferPage from "../pages/Offer";
import { ToastProvider } from "../components/ui/Toast";

const getComparison = vi.fn();
const saveWeights = vi.fn();
const getWeights = vi.fn();

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      listOffers: vi.fn(),
      listCities: vi.fn(),
      getWeights: (...a: unknown[]) => getWeights(...a),
      saveWeights: (...a: unknown[]) => saveWeights(...a),
      getComparison: (...a: unknown[]) => getComparison(...a),
      listApplications: vi.fn(),
      deleteOffer: vi.fn(),
      acceptOffer: vi.fn(),
    },
  };
});

import { api } from "../api/client";

const OFFERS = [
  { offer_id: 1, company: "麦浪文化", job_title: "用户增长", status: "active", status_label: "在比较中" },
  { offer_id: 2, company: "云枢科技", job_title: "产品运营", status: "active", status_label: "在比较中" },
  { offer_id: 3, company: "星野数据", job_title: "内容运营", status: "active", status_label: "在比较中" },
] as unknown as OfferOut[];

/** 造一次 comparison 响应：分数与名次由参数决定，其余字段按类型填满。 */
function comparison(
  scores: Record<string, { score: number; rank: number }>,
  weights: Record<string, number>,
): ComparisonResult {
  return {
    comparison_id: "cmp",
    offers: OFFERS.map((o) => {
      // 表里没写到的公司视为 0 分 —— 让"分数没按预期更新"能直接断言出来，
      // 而不是在 helper 里抛异常
      const s = scores[o.company] ?? { score: 0, rank: 0 };
      return {
        offer_id: o.offer_id,
        company: o.company,
        job_title: o.job_title,
        city: null,
        status: o.status,
        dimension_scores: {},
        composite_score: s.score,
        rank: s.rank,
      };
    }),
    weights,
    weight_snapshot: weights,
    city_costs: {},
    analysis: { recommendations: [], ai_status: "ok" },
  };
}

// Case A：Demo 默认偏好「成长优先」下的分数
const GROWTH = { economic: 15, disposable: 10, workload: 10, stability: 10, growth: 40, match: 15 };
const GROWTH_SCORES = {
  麦浪文化: { score: 83.7, rank: 1 },
  云枢科技: { score: 82.13, rank: 2 },
  星野数据: { score: 72.6, rank: 3 },
};
// Case B：换成「稳定优先」后，分数与名次都变了（麦浪掉到第 3）
const STABILITY = { economic: 15, disposable: 10, workload: 15, stability: 35, growth: 15, match: 10 };
const STABILITY_SCORES = {
  云枢科技: { score: 80.98, rank: 1 },
  星野数据: { score: 78.95, rank: 2 },
  麦浪文化: { score: 72.55, rank: 3 },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <OfferPage />
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("Offer 决策偏好 → 综合分重算", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.listOffers as ReturnType<typeof vi.fn>).mockResolvedValue({ items: OFFERS, total: OFFERS.length });
    (api.listCities as ReturnType<typeof vi.fn>).mockResolvedValue({ cities: [], user_overrides: [] });
    (api.listApplications as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [] });
    getWeights.mockResolvedValue({ weights: GROWTH, preset_name: "growth" });
    getComparison.mockResolvedValue(comparison(GROWTH_SCORES, GROWTH));
    saveWeights.mockResolvedValue({ weights: STABILITY, preset_name: "stability" });
  });

  it("挂载时按已存偏好拉一次分数，并渲染出来", async () => {
    renderPage();
    await waitFor(() => expect(getComparison).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("83.7")).toBeInTheDocument();
    expect(screen.getByText("第 1 名")).toBeInTheDocument();
  });

  it("选择预设后：先落库、再重算、并把新分数渲染出来", async () => {
    renderPage();
    await waitFor(() => expect(getComparison).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("83.7")).toBeInTheDocument();

    // 第二次拉取换成「稳定优先」的结果
    getComparison.mockResolvedValue(comparison(STABILITY_SCORES, STABILITY));

    fireEvent.click(screen.getByText("稳定优先"));

    // ① 权重确实落库了
    await waitFor(() => expect(saveWeights).toHaveBeenCalledWith(
      expect.objectContaining({ preset_name: "stability" }),
    ));

    // ② 综合分被重新拉取（这是线上缺失的一环）
    await waitFor(() => expect(getComparison.mock.calls.length).toBeGreaterThanOrEqual(2));

    // ③ 顺序：重算发生在落库**之后** —— 否则拉到的仍是旧权重
    //    （上面已经断言过两者都被调用过，这里的取下标是安全的）
    const saveOrder = saveWeights.mock.invocationCallOrder[0]!;
    const refetchOrder = getComparison.mock.invocationCallOrder[1]!;
    expect(refetchOrder).toBeGreaterThan(saveOrder);

    // ④ 新分数与新名次真的渲染出来了（不只是"请求发了"）
    await waitFor(() => expect(screen.getByText("80.98")).toBeInTheDocument());
    expect(screen.queryByText("83.7")).not.toBeInTheDocument();
    // 麦浪文化从第 1 名掉到第 3 名
    expect(screen.getByText("第 3 名")).toBeInTheDocument();
  });

  it("重复选同一个预设，分数保持一致（结果确定）", async () => {
    renderPage();
    await waitFor(() => expect(getComparison).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("83.7")).toBeInTheDocument();

    fireEvent.click(screen.getByText("均衡方案"));
    await waitFor(() => expect(getComparison.mock.calls.length).toBeGreaterThanOrEqual(2));

    const before = getComparison.mock.calls.length;
    fireEvent.click(screen.getByText("均衡方案"));
    await waitFor(() => expect(getComparison.mock.calls.length).toBeGreaterThan(before));

    // 每次拿到的都是同一个响应，页面分数不应抖动
    expect(screen.getByText("83.7")).toBeInTheDocument();
  });

  it("保存失败时不做重算，避免把旧权重算出的分数当成「已生效」", async () => {
    renderPage();
    await waitFor(() => expect(getComparison).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("83.7")).toBeInTheDocument();

    saveWeights.mockRejectedValue(new Error("网络错误"));
    fireEvent.click(screen.getByText("薪资优先"));

    await waitFor(() => expect(saveWeights).toHaveBeenCalled());
    // 落库没成功 → 不该重新拉取（否则会拿"后端还存着的旧权重"覆盖显示，误导用户）
    expect(getComparison).toHaveBeenCalledTimes(1);
    expect(screen.getByText("83.7")).toBeInTheDocument();
  });
});
