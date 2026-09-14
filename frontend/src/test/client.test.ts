import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, clearToken, getToken, setToken } from "../api/client";

// 关键回归：带 token 的请求收到 401 时，除了清 localStorage，还必须广播
// cdp:auth-expired —— AuthContext 靠它同步清空 React 状态（P1 修复的核心）。
describe("api client 401 handling", () => {
  let expiredListener: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    expiredListener = vi.fn();
    window.addEventListener("cdp:auth-expired", expiredListener);
  });

  afterEach(() => {
    window.removeEventListener("cdp:auth-expired", expiredListener);
    vi.restoreAllMocks();
  });

  function mockFetchOnce(status: number, body: unknown) {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        })
      )
    );
  }

  it("401 with token: clears token AND broadcasts auth-expired", async () => {
    setToken("stale-token");
    mockFetchOnce(401, { error: { code: "unauthorized", message: "token 失效" } });

    await expect(api.me()).rejects.toBeInstanceOf(ApiError);

    expect(getToken()).toBeNull();
    expect(expiredListener).toHaveBeenCalledTimes(1);
  });

  it("401 without token (e.g. wrong password): no broadcast, no token side effects", async () => {
    mockFetchOnce(401, { error: { code: "unauthorized", message: "账号或密码错误" } });

    await expect(api.login({ identifier: "a@b.c", password: "wrong" })).rejects.toBeInstanceOf(
      ApiError
    );

    expect(expiredListener).not.toHaveBeenCalled();
    expect(getToken()).toBeNull();
  });

  it("other error statuses: token untouched, no broadcast", async () => {
    setToken("valid-token");
    mockFetchOnce(500, { error: { code: "server_error", message: "boom" } });

    await expect(api.getProfile()).rejects.toBeInstanceOf(ApiError);

    expect(getToken()).toBe("valid-token");
    expect(expiredListener).not.toHaveBeenCalled();
    clearToken();
  });
});
