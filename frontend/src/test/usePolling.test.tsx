import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { usePolling } from "../hooks/usePolling";

describe("usePolling", () => {
  it("polls until decide returns done, then calls onDone", async () => {
    let calls = 0;
    const onDone = vi.fn();

    const { result } = renderHook(() =>
      usePolling<number>({
        fetch: () => {
          calls += 1;
          return Promise.resolve(calls);
        },
        decide: (n) => (n >= 3 ? "done" : "continue"),
        onDone,
        intervalMs: 10,
      })
    );

    result.current.start();

    await waitFor(() => expect(onDone).toHaveBeenCalledWith(3));
    expect(calls).toBe(3);
  });

  it("gives up after maxAttempts (network errors also count)", async () => {
    const onDone = vi.fn();
    const onGiveUp = vi.fn();

    const { result } = renderHook(() =>
      usePolling<number>({
        fetch: () => Promise.reject(new Error("down")),
        decide: () => "continue",
        onDone,
        onGiveUp,
        intervalMs: 10,
        maxAttempts: 3,
      })
    );

    result.current.start();

    await waitFor(() => expect(onGiveUp).toHaveBeenCalledWith("max-attempts"));
    expect(onDone).not.toHaveBeenCalled();
  });

  it("give-up verdict stops polling immediately", async () => {
    const onDone = vi.fn();
    const onGiveUp = vi.fn();

    const { result } = renderHook(() =>
      usePolling<string>({
        fetch: () => Promise.resolve("failed"),
        decide: (r) => (r === "failed" ? "give-up" : "continue"),
        onDone,
        onGiveUp,
        intervalMs: 10,
        maxAttempts: 99,
      })
    );

    result.current.start();

    await waitFor(() => expect(onGiveUp).toHaveBeenCalledWith("aborted"));
    expect(onDone).not.toHaveBeenCalled();
  });

  it("stop() cancels further polling", async () => {
    let calls = 0;
    const onDone = vi.fn();

    const { result } = renderHook(() =>
      usePolling<number>({
        fetch: () => {
          calls += 1;
          return Promise.resolve(calls);
        },
        decide: () => "continue",
        onDone,
        intervalMs: 10,
        maxAttempts: 100,
      })
    );

    result.current.start();
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(1));
    result.current.stop();

    const atStop = calls;
    await new Promise((r) => setTimeout(r, 50));
    expect(calls).toBe(atStop);
  });
});
