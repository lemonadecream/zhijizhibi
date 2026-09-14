import { useCallback, useEffect, useRef } from "react";
import { api, type F1Parsed, type ResumeStatus } from "../api/client";

const DEFAULT_INTERVAL_MS = 1000;
const DEFAULT_MAX_ATTEMPTS = 60;

export type PollVerdict = "done" | "continue" | "give-up";
export type GiveUpReason = "max-attempts" | "aborted";

interface UsePollingOptions<T> {
  fetch: () => Promise<T>;
  /** 每次结果回来时判定：完成 / 继续 / 放弃（如解析失败状态） */
  decide: (result: T, attempt: number) => PollVerdict;
  onDone: (result: T) => void;
  /** 达到次数上限或 decide 判定放弃时回调 */
  onGiveUp?: (reason: GiveUpReason) => void;
  intervalMs?: number;
  maxAttempts?: number;
}

/**
 * 轮询 hook：统一了"1 秒一轮、失败重试"的散落实现，并补上此前缺失的
 * 关键保护——最大尝试次数。网络错误同样计数：后端长时间不可达时停止盲等，
 * 而不是无限打下去。组件卸载自动停止。
 */
export function usePolling<T>(opts: UsePollingOptions<T>) {
  const timerRef = useRef<number | null>(null);
  const attemptRef = useRef(0);
  // 始终读最新闭包，调用方无需担心回调过期
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const stop = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => stop, [stop]);

  const start = useCallback(() => {
    stop();
    attemptRef.current = 0;
    const max = optsRef.current.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
    const interval = optsRef.current.intervalMs ?? DEFAULT_INTERVAL_MS;

    const tick = () => {
      attemptRef.current += 1;
      optsRef.current
        .fetch()
        .then((result) => {
          const verdict = optsRef.current.decide(result, attemptRef.current);
          if (verdict === "done") {
            stop();
            optsRef.current.onDone(result);
            return;
          }
          if (verdict === "give-up" || attemptRef.current >= max) {
            stop();
            optsRef.current.onGiveUp?.(verdict === "give-up" ? "aborted" : "max-attempts");
            return;
          }
          timerRef.current = window.setTimeout(tick, interval);
        })
        .catch(() => {
          // 网络错误也计入次数，避免后端不可达时无限轮询
          if (attemptRef.current >= max) {
            stop();
            optsRef.current.onGiveUp?.("max-attempts");
            return;
          }
          timerRef.current = window.setTimeout(tick, interval);
        });
    };
    tick();
  }, [stop]);

  return { start, stop };
}

const RESUME_POLL_MAX_ATTEMPTS = 90; // 90s：真实 AI 解析通常 10-40s，超时视为异常

/**
 * 简历解析状态轮询：此前在 Profile / ResumeFlow / ResumeInline / ScratchInput
 * 四处复制了近乎相同的实现，这里是唯一版本（统一 90s 上限）。
 */
export function useResumeParsePolling(handlers: {
  onParsed: (parsed: F1Parsed) => void;
  onFailed: (message: string) => void;
}) {
  const idRef = useRef<number | null>(null);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const polling = usePolling<ResumeStatus>({
    fetch: () => api.getResume(idRef.current!),
    decide: (r) => {
      if (r.parse_status === "parsed" && r.parsed_json) return "done";
      if (r.parse_status === "failed") return "give-up";
      return "continue";
    },
    onDone: (r) => {
      if (r.parsed_json) handlersRef.current.onParsed(r.parsed_json);
      else handlersRef.current.onFailed("解析结果为空，请改用其他录入方式。");
    },
    onGiveUp: (reason) => {
      handlersRef.current.onFailed(
        reason === "max-attempts"
          ? "解析等待超时，请稍后重试或改用其他录入方式。"
          : "解析失败，请重试或改用其他录入方式。"
      );
    },
    maxAttempts: RESUME_POLL_MAX_ATTEMPTS,
  });
  const { start: startInner, stop } = polling;

  const start = useCallback(
    (resumeId: number) => {
      idRef.current = resumeId;
      startInner();
    },
    [startInner]
  );

  return { start, stop };
}
