/**
 * Demo 访谈页「三层结构」回归 —— 回答区必须永远贴在视口底部。
 *
 * 线上验收发现的问题：回复一多，回答/输入区就被消息一路顶出屏幕。
 * 根因是外层用了 `min-height: 100vh`（flex 列容器高度仍由内容决定），
 * 内部 .dmo-scroll 的 flex:1 于是跟着内容长高，overflow-y:auto 永不触发。
 * 修法是确定高度 + 明确的 viewport / chat-content / composer 三层。
 *
 * ⚠️ 为什么这里只测结构、不测像素：
 * vitest 跑在 jsdom 上，**没有排版引擎**（offsetHeight / getComputedStyle 的
 * 布局值全是 0 或空），所以"输入框是否真的停在底部"无法在此自证 —— 那需要
 * 浏览器里的真实截图验收。本文件锁的是 **让固定底部成立的结构契约**：
 * 只要 composer 是滚动容器之外的兄弟节点，它在任何 CSS 高度下都不可能
 * 被消息内容推走。结构一旦被改回"嵌在滚动区里"，这里立刻报红。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import DemoInterviewPage from "../pages/DemoInterview";

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

function enterInterview() {
  fireEvent.click(screen.getByRole("button", { name: /从认识自己开始/ }));
}

async function sendOnce(text?: string) {
  const box = screen.getByLabelText("你的回答") as HTMLTextAreaElement;
  if (text) fireEvent.change(box, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(screen.queryByText("正在读你刚才说的话…")).not.toBeInTheDocument(), {
    timeout: 4000,
  });
}

describe("Demo 访谈页 · chat composer 固定底部（三层结构）", () => {
  it("首屏：viewport 层带 dmo--intro，极光背景挂上、此时没有回答区", () => {
    const { container } = renderPage();
    const shell = container.querySelector(".dmo");
    expect(shell).not.toBeNull();
    // 首屏态：CSS 据此挂上极淡蓝紫极光背景
    expect(shell!.className).toContain("dmo--intro");
    expect(shell!.className).not.toContain("dmo--chat");

    // 极光 SVG 存在（AuroraBackdrop 内部的 radialGradient id 是稳定锚点，
    // 避免在 jsdom 里用"是否有 svg"这种会被 Icon 干扰的判断）
    expect(container.querySelector("#au-1")).not.toBeNull();

    // 首屏还没有进入访谈，回答区不该存在
    expect(container.querySelector(".dmo-composer")).toBeNull();
  });

  it("进入访谈后：viewport 层切到 dmo--chat，极光撤下，滚动区与回答区同时存在", async () => {
    const { container } = renderPage();
    enterInterview();
    await waitFor(() => expect(container.querySelector(".dmo-scroll")).not.toBeNull());

    const shell = container.querySelector(".dmo")!;
    expect(shell.className).toContain("dmo--chat");
    expect(shell.className).not.toContain("dmo--intro");
    expect(container.querySelector(".dmo-composer")).not.toBeNull();
    // 访谈态换成干净底色：AI/用户气泡才是主角，氛围不抢注意力
    expect(container.querySelector("#au-1")).toBeNull();
  });

  it("回答区是滚动容器的**兄弟**节点，而不是它的子节点", async () => {
    const { container } = renderPage();
    enterInterview();
    await waitFor(() => expect(container.querySelector(".dmo-scroll")).not.toBeNull());

    const scroll = container.querySelector(".dmo-scroll")!;
    const composer = container.querySelector(".dmo-composer")!;

    // ① 两者同父 —— 同属 .dmo-main 这一层弹性列容器
    expect(scroll.parentElement).toBe(composer.parentElement);
    expect(scroll.parentElement!.className).toContain("dmo-main");

    // ② 回答区**不在**滚动容器内部。这是"输入框不会被消息顶出屏幕"的结构保证：
    //    消息只在 scroll 里增长，composer 在 scroll 之外，二者互不影响。
    expect(scroll.contains(composer)).toBe(false);

    // ③ 顺序：滚动区在前、回答区在后 —— 视觉上内容在上、输入在下
    const siblings = Array.from(scroll.parentElement!.children);
    expect(siblings.indexOf(scroll)).toBeLessThan(siblings.indexOf(composer));

    // ④ 回答区必须是 .dmo-main 的最后一个元素，即真正"贴底"而不是被别的块挤在中间
    expect(scroll.parentElement!.lastElementChild).toBe(composer);
  });

  it("顶栏在滚动容器之外：页头不会跟着消息一起滚走", async () => {
    const { container } = renderPage();
    enterInterview();
    await waitFor(() => expect(container.querySelector(".dmo-scroll")).not.toBeNull());

    const scroll = container.querySelector(".dmo-scroll")!;
    const topbar = container.querySelector(".dmo-topbar")!;
    // 顶栏是 .dmo 的直接子元素，与 main 平级 → 不参与滚动
    expect(topbar.parentElement!.className).toContain("dmo");
    expect(topbar.contains(scroll)).toBe(false);
    expect(scroll.parentElement!.contains(topbar)).toBe(false);
  });

  it("新增固定布局后，多轮交互不被破坏：连发多轮回答区始终在、且消息持续累加", async () => {
    const { container } = renderPage();
    enterInterview();
    await waitFor(() => expect(container.querySelector(".dmo-scroll")).not.toBeNull());

    const scroll = container.querySelector(".dmo-scroll")!;
    const countBubbles = () => scroll.querySelectorAll(".dmo-bubble").length;

    const afterFirst = countBubbles();
    expect(afterFirst).toBeGreaterThan(0);

    for (let i = 1; i <= 3; i++) {
      await sendOnce(`第 ${i} 轮补充：这部分是我主要负责的，后面也有了变化。`);
      // 每轮结束后回答区都必须仍然存在，且依旧是滚动区的兄弟节点
      const composer = container.querySelector(".dmo-composer");
      expect(composer).not.toBeNull();
      expect(scroll.contains(composer!)).toBe(false);
      // 消息只往滚动容器里加，回答区本身不参与
      expect(countBubbles()).toBeGreaterThan(afterFirst);
    }

    // 输入框仍然可用：清空后按钮回到 disabled，重新输入又能发送
    const box = screen.getByLabelText("你的回答") as HTMLTextAreaElement;
    expect(box.value).toBe("");
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
    fireEvent.change(box, { target: { value: "还能继续说。" } });
    expect(screen.getByRole("button", { name: "发送" })).toBeEnabled();
  }, 20000);
});
