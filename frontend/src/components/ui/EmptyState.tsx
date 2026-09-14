import type { ReactNode } from "react";
import Icon from "./Icon";

interface EmptyStateProps {
  icon?: string;
  /** 大幅 SVG 插画（传入时替代小图标位，用于页面级空态） */
  illustration?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export default function EmptyState({ icon = "info", illustration, title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {illustration ? (
        <div className="empty-illustration">{illustration}</div>
      ) : (
        <div className="empty-icon">
          <Icon name={icon} size={24} />
        </div>
      )}
      <div className="empty-title">{title}</div>
      {description && <div className="empty-desc">{description}</div>}
      {action && <div className="actions" style={{ justifyContent: "center" }}>{action}</div>}
    </div>
  );
}
