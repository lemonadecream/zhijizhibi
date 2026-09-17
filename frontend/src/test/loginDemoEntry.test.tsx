/**
 * 登录页「体验 Demo」入口回归测试（Step 3）。
 *
 * 这一步的硬约束是"**不新增 Demo 专属 Auth / API / 路由 / 权限**"，所以测试要钉住的
 * 不是"按钮长什么样"，而是**它走的是不是那条唯一的登录链路**：
 *
 * 1. 点击后调用的是同一个 `api.login`，凭据就是公开演示账号；
 * 2. 落点是 `/demo-interview`（「AI 认识你」冷启动访谈），且**不触碰**
 *    `api.getOnboardingSession`（不参与 onboarding 判定，
 *    因此绝不会被丢进 onboarding）；
 * 3. 普通账号的登录/注册路径逐字未变：仍走 `getOnboardingSession` 分流
 *    （finalized → /profile，否则 → /onboarding）；
 * 4. 演示账号不可用时只提示错误，不跳转、不产生半登录状态。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      login: vi.fn(),
      me: vi.fn(),
      getOnboardingSession: vi.fn(),
    },
  };
});

import { ApiError, api } from "../api/client";
import { AuthProvider } from "../context/AuthContext";
import Login from "../pages/Login";

const DEMO_EMAIL = "demo@zhijizhibi.app";
const DEMO_PASSWORD = "demo123456";

type Mocked = {
  login: ReturnType<typeof vi.fn>;
  me: ReturnType<typeof vi.fn>;
  getOnboardingSession: ReturnType<typeof vi.fn>;
};
const m = api as unknown as Mocked;

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<div>REGISTER_PAGE</div>} />
          <Route path="/profile" element={<div>PROFILE_PAGE</div>} />
          <Route path="/demo-interview" element={<div>DEMO_INTERVIEW_PAGE</div>} />
          <Route path="/onboarding" element={<div>ONBOARDING_PAGE</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

/** 填普通账号表单并提交。 */
function submitCredentials(identifier: string, password: string) {
  fireEvent.change(screen.getByLabelText("邮箱或手机号"), { target: { value: identifier } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  m.login.mockResolvedValue({ access_token: "demo-token" });
  m.me.mockResolvedValue({ user_id: 40, email: DEMO_EMAIL });
  m.getOnboardingSession.mockResolvedValue({ status: "finalized" });
});

afterEach(() => {
  localStorage.clear();
});

describe("登录页 · 体验 Demo 入口", () => {
  it("展示入口与辅助说明，且是独立的 button（不提交表单）", () => {
    renderLogin();
    const btn = screen.getByRole("button", { name: /体验 Demo/ });
    expect(btn).toHaveAttribute("type", "button");
    expect(screen.getByText("无需注册 · 使用演示数据")).toBeInTheDocument();
    // 普通登录入口同时存在，未被替换
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
  });

  it("点击后用演示账号走同一个登录接口，并进入「AI 认识你」冷启动访谈", async () => {
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /体验 Demo/ }));

    await waitFor(() => expect(screen.getByText("DEMO_INTERVIEW_PAGE")).toBeInTheDocument());

    expect(m.login).toHaveBeenCalledTimes(1);
    expect(m.login).toHaveBeenCalledWith({ identifier: DEMO_EMAIL, password: DEMO_PASSWORD });
    // 未登录 token 已持久化，后续页面读取 Step 2 数据靠的就是它
    expect(localStorage.getItem("cdp_token")).toBe("demo-token");
    // 冷启动访谈是过程页，不该直接落到画像
    expect(screen.queryByText("PROFILE_PAGE")).not.toBeInTheDocument();
  });

  it("Demo 入口不做 onboarding 判定，因此不会被丢进 onboarding", async () => {
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /体验 Demo/ }));

    await waitFor(() => expect(screen.getByText("DEMO_INTERVIEW_PAGE")).toBeInTheDocument());
    expect(m.getOnboardingSession).not.toHaveBeenCalled();
    expect(screen.queryByText("ONBOARDING_PAGE")).not.toBeInTheDocument();
  });

  it("演示账号不可用时只提示错误，不跳转也不留下 token", async () => {
    m.login.mockRejectedValue(new ApiError("演示账号暂时不可用", "demo_unavailable", 500));
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /体验 Demo/ }));

    await waitFor(() =>
      expect(screen.getByText("演示账号暂时不可用")).toBeInTheDocument()
    );
    expect(screen.queryByText("DEMO_INTERVIEW_PAGE")).not.toBeInTheDocument();
    expect(localStorage.getItem("cdp_token")).toBeNull();
  });
});

describe("登录页 · 普通账号流程未被改变", () => {
  it("普通登录仍走 onboarding 判定：已生成画像 -> /profile", async () => {
    renderLogin();
    submitCredentials("someone@example.com", "pw123456");

    await waitFor(() => expect(screen.getByText("PROFILE_PAGE")).toBeInTheDocument());
    expect(m.login).toHaveBeenCalledWith({ identifier: "someone@example.com", password: "pw123456" });
    expect(m.getOnboardingSession).toHaveBeenCalledTimes(1);
  });

  it("普通登录未生成画像 -> /onboarding", async () => {
    m.getOnboardingSession.mockResolvedValue({ status: "in_progress" });
    renderLogin();
    submitCredentials("newbie@example.com", "pw123456");

    await waitFor(() => expect(screen.getByText("ONBOARDING_PAGE")).toBeInTheDocument());
    expect(m.getOnboardingSession).toHaveBeenCalledTimes(1);
  });

  it("普通登录失败仍显示后端错误文案", async () => {
    m.login.mockRejectedValue(new ApiError("邮箱或密码错误", "invalid_credentials", 401));
    renderLogin();
    submitCredentials("someone@example.com", "wrong");

    await waitFor(() => expect(screen.getByText("邮箱或密码错误")).toBeInTheDocument());
    expect(screen.queryByText("PROFILE_PAGE")).not.toBeInTheDocument();
  });
});
