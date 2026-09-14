import { useAiConfig } from "../context/AiConfigContext";

type Tone = "real" | "demo" | "degraded";

interface Props {
  /** Per-result AI status from the backend. "ok" means the real provider
   *  produced it; anything else (e.g. "fallback" or missing) means the
   *  deterministic template was used. Optional when the surface has no
   *  per-result status (e.g. config-only demo state). */
  aiStatus?: string;
  /** Optional contextual label override, e.g. "AI 提炼" / "AI 解析" /
   *  "AI 关系识别" / "AI 建议". Falls back to the honest status label. */
  label?: string;
}

/**
 * Lightweight, honest AI status badge (P0-1).
 *
 * Folds the global provider config + the per-result AI status into three states:
 *   - real     : 真实 AI 辅助
 *   - demo     : AI 辅助 · 演示模式        (mock provider)
 *   - degraded : AI 辅助 · 已降级          (real provider but no key / call failed)
 *
 * It never pretends fallback output is "real AI". It only labels what actually
 * happened, so users can trust the AI 辅助 mark.
 */
export default function AiBadge({ aiStatus, label }: Props) {
  const { aiProvider, aiAvailable } = useAiConfig();

  const degraded = aiStatus !== "ok";
  let tone: Tone;
  let statusLabel: string;
  if (aiProvider === "mock") {
    tone = "demo";
    statusLabel = "AI 辅助 · 演示模式";
  } else if (!aiAvailable || degraded) {
    tone = "degraded";
    statusLabel = "AI 辅助 · 已降级";
  } else {
    tone = "real";
    statusLabel = "AI 辅助";
  }

  const text = label ?? statusLabel;

  return (
    <span className={`ai-badge ai-badge--${tone}`} title={statusLabel}>
      <span className="ai-badge__dot" />
      {text}
    </span>
  );
}
