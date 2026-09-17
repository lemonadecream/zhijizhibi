/**
 * 「AI 认识你」Demo 冷启动页的组件级回归。
 *
 * 这个页面是唯一新增的交互流程，且**不回写任何后端状态**
 * （Demo 账号多人共用，走 interview_step 会互相污染会话），
 * 因此它的正确性只能靠组件测试锁住。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import DemoInterviewPage from "../pages/DemoInterview";
import { TOTAL_TURNS } from "../pages/DemoInterview/demoScript";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: {} };
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/demo-interview"]}>
      <Routes>
        <Route path="/demo-interview" element={<DemoInterviewPage />} />
        <Route path="/profile" element={<div>PROFILE_PAGE</div>} />
      </Routes>
    </MemoryRouter>
  );
}

/** 发送一条回答（用预填内容或手动输入）。 */
async function sendOnce(text?: string) {
  const box = screen.getByLabelText("你的回答") as HTMLTextAreaElement;
  if (text) fireEvent.change(box, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(screen.queryByText("正在读你刚才说的话…")).not.toBeInTheDocument(), {
    timeout: 4000,
  });
}

/** 走完整个访谈。 */
async function runFullInterview() {
  for (let i = 1; i <= TOTAL_TURNS; i++) {
    await sendOnce(i === 1 ? undefined : `第 ${i} 轮补充：我负责的部分是这样，后来也有了变化。`);
  }
}

describe("Demo 冷启动访谈页", () => {
  it("首屏只保留一个主 CTA，辅助入口不与主 CTA 平级", () => {
    renderPage();
    expect(screen.getByText("先花几分钟，让 AI 认识你")).toBeInTheDocument();

    // 唯一主入口
    expect(screen.getByRole("button", { name: /从认识自己开始/ })).toBeInTheDocument();
    // 已移除四张并列引导卡
    expect(screen.queryByRole("button", { name: /从实习经历开始/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /从项目经历开始/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /说说你喜欢什么样的工作/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /让 AI 带着你聊/ })).not.toBeInTheDocument();

    expect(screen.getByRole("button", { name: /跳过/ })).toBeInTheDocument();
  });

  it("说明当前是固定数据演示，并指向注册后的真实 AI", () => {
    renderPage();
    expect(screen.getByText(/在线 Demo · 固定数据演示/)).toBeInTheDocument();
    expect(screen.getByText(/想体验真实 AI 对话？注册后即可开始/)).toBeInTheDocument();
    // 辅助的简历入口保留，但只是小字提示
    expect(screen.getByText(/也可以稍后上传简历/)).toBeInTheDocument();
  });

  it("点击主 CTA 后进入访谈并预填示例回答", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /从认识自己开始/ }));

    const box = screen.getByLabelText("你的回答") as HTMLTextAreaElement;
    expect(box.value.length).toBeGreaterThan(30);
    expect(screen.getByRole("button", { name: "发送" })).toBeEnabled();
    expect(screen.getByText(`第 1 / ${TOTAL_TURNS} 轮`)).toBeInTheDocument();
  });

  it("总轮次为 8 轮（7-8 轮有效问答）", () => {
    expect(TOTAL_TURNS).toBeGreaterThanOrEqual(7);
    expect(TOTAL_TURNS).toBeLessThanOrEqual(8);
  });

  it("后续追问会引用用户上一轮说的话（上下文相关）", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /从认识自己开始/ }));

    await sendOnce("我之前在云枢科技实习，负责客户反馈整理，最后有 30 条需求进了版本。");
    // 追问里应引用从这句话抽取出的主体（用户气泡里也有云枢，故用 findAll）
    expect(screen.getAllByText(/云枢/).length).toBeGreaterThan(1);
  });

  it("连续 8 轮对话走到收束，随后可进入职业画像", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /从认识自己开始/ }));

    await runFullInterview();

    await waitFor(
      () => expect(screen.getByRole("button", { name: /查看 AI 给我的职业画像/ })).toBeInTheDocument(),
      { timeout: 8000 }
    );

    fireEvent.click(screen.getByRole("button", { name: /查看 AI 给我的职业画像/ }));
    await waitFor(() => expect(screen.getByText("PROFILE_PAGE")).toBeInTheDocument());
  }, 20000);

  it("最后一轮先复述理解并指出不确定项，而不是直接生成画像", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /从认识自己开始/ }));

    // 第 1~6 轮回答后，第 8 轮（TOTAL_TURNS）的「理解确认」问句应当出现
    for (let i = 1; i <= TOTAL_TURNS - 2; i++) {
      await sendOnce(i === 1 ? undefined : `第 ${i} 轮补充：我负责的部分是这样。`);
    }

    await sendOnce("我更喜欢自己推进，但目标需要别人讲清楚。");
    expect(screen.getByText(/我大概理了一下/)).toBeInTheDocument();
    expect(screen.getByText(/有两点我还不确定/)).toBeInTheDocument();
    // 确认问句出现时，访谈尚未收束，画像 CTA 不该存在
    expect(screen.queryByRole("button", { name: /查看 AI 给我的职业画像/ })).not.toBeInTheDocument();
  }, 20000);

  it("「跳过，直接看 Demo 画像」始终可用，直接进入画像页", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /跳过，直接看 Demo 画像/ }));
    await waitFor(() => expect(screen.getByText("PROFILE_PAGE")).toBeInTheDocument());
  });
});
