import type { ReactNode } from "react";
import Button from "../ui/Button";
import AiBadge from "../AiBadge";
import EvidenceBlock from "./EvidenceBlock";

interface AIResultBlockProps {
  title?: string;
  evidence?: string;
  onRegenerate?: () => void;
  regenerating?: boolean;
  aiStatus?: string;
  badgeLabel?: string;
  children: ReactNode;
}

// AI 结果统一展示块:浅紫 AI 标识(诚实状态) + 上下文标题 + 依据 + 可重新生成。
// 强调:AI 输出是可理解、可解释、可修改、可重新生成的,不是不可改的结论。
export default function AIResultBlock({
  title,
  evidence,
  onRegenerate,
  regenerating = false,
  aiStatus,
  badgeLabel,
  children,
}: AIResultBlockProps) {
  return (
    <div className="ai-block">
      <div className="ai-block-header">
        <AiBadge aiStatus={aiStatus} label={badgeLabel} />
        {title && <span className="secondary" style={{ fontSize: "var(--text-sm)" }}>{title}</span>}
        {onRegenerate && (
          <Button variant="ghost" size="sm" icon="refresh" onClick={onRegenerate} disabled={regenerating}>
            {regenerating ? "生成中…" : "重新生成"}
          </Button>
        )}
      </div>
      <div className="ai-block-content">{children}</div>
      {evidence && (
        <div className="mt-4">
          <EvidenceBlock text={evidence} />
        </div>
      )}
    </div>
  );
}
