import { useEffect, useState } from "react";

interface LoadingStateProps {
  label?: string;
  inline?: boolean;
  skeleton?: boolean;
  lines?: number;
  /**
   * 阶段文案：传入多步文案时按序轮换（每 2.6s 一步），
   * 让 AI 解析/生成这类 10-40s 的等待"可感知、有预期"。
   */
  stages?: string[];
}

export default function LoadingState({
  label = "加载中…",
  inline = false,
  skeleton = false,
  lines = 3,
  stages,
}: LoadingStateProps) {
  const [stageIdx, setStageIdx] = useState(0);

  useEffect(() => {
    if (!stages || stages.length < 2) return;
    const timer = window.setInterval(() => {
      setStageIdx((i) => (i + 1) % stages.length);
    }, 2600);
    return () => window.clearInterval(timer);
  }, [stages]);

  if (skeleton) {
    return (
      <div className={`loading-state ${inline ? "loading-state--inline" : ""}`} style={{ gap: 12 }}>
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 56, width: "100%" }} />
        ))}
      </div>
    );
  }
  return (
    <div className={`loading-state ${inline ? "loading-state--inline" : ""}`}>
      <span className="ui-spinner" />
      <span>{stages && stages.length > 0 ? stages[Math.min(stageIdx, stages.length - 1)] : label}</span>
    </div>
  );
}
