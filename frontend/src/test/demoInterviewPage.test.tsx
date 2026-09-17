/**
 * 「AI 认识你」Demo 冷启动页的组件级回归。
 *
 * 这个页面是本轮唯一新增的交互流程，且**不回写任何后端状态**
 * （Demo 账号多人共用，走 interview_step 会互相污染会话），
 * 因此它的正确性只能靠组件测试锁住。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import DemoInterviewPage from "../pages/DemoInterview";
import { DEMO_GUIDES, TOTAL_TURNS, type DemoGuide } from "../pages/DemoInterview/demoScript";

/** 四个引导项里的第一个，用于"选一个引导分支"的用例。 */
const GUIDE = DEMO_GUIDES[0] as DemoGuide;

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

describe("Demo 冷启动访谈页", () => {
  it("首屏给出四个冷启动引导项与「跳过」出口，不要求上传简历", () => {
    renderPage();
    expect(screen.getByText("先花 1 分钟，让 AI 认识你")).toBeInTheDocument();
    for (const g of DEMO_GUIDES) {
      expect(screen.getByRole("button", { name: new RegExp(g.label) })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /跳过/ })).toBeInTheDocument();
    // 明确告知不需要上传简历
    expect(screen.getByText(/不需要注册、不需要上传简历/)).toBeInTheDocument();
  });

  it("选中引导后预填示例回答，可直接发送", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: new RegExp(GUIDE.label) }));

    // AI 先给出该分支的开场白
    expect(screen.getByText(GUIDE.opener)).toBeInTheDocument();
    // 输入框已预填，因此"发送"可点
    const box = screen.getByLabelText("你的回答") as HTMLTextAreaElement;
    expect(box.value).toBe(GUIDE.example);
    expect(screen.getByRole("button", { name: "发送" })).toBeEnabled();
  });

  it("连续对话走到收束，随后可进入职业画像", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: new RegExp(GUIDE.label) }));

    // 第 1 轮用预填示例，之后每轮手输
    await sendOnce();
    for (let i = 2; i < TOTAL_TURNS; i++) await sendOnce(`第 ${i} 轮补充内容`);

    // 第 TOTAL_TURNS 轮之后应出现收束 CTA
    await sendOnce("最后一轮补充内容");
    await waitFor(
      () => expect(screen.getByRole("button", { name: /查看 AI 给我的职业画像/ })).toBeInTheDocument(),
      { timeout: 4000 }
    );

    fireEvent.click(screen.getByRole("button", { name: /查看 AI 给我的职业画像/ }));
    await waitFor(() => expect(screen.getByText("PROFILE_PAGE")).toBeInTheDocument());
  });

  it("「跳过，直接看 Demo 画像」始终可用，直接进入画像页", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /跳过，直接看 Demo 画像/ }));
    await waitFor(() => expect(screen.getByText("PROFILE_PAGE")).toBeInTheDocument());
  });
});
