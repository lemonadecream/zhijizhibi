import type { ReactNode } from "react";

type CardVariant = "default" | "hero" | "section" | "flat" | "ai";

interface CardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  hover?: boolean;
  variant?: CardVariant;
  className?: string;
  children: ReactNode;
}

/**
 * Card — 视觉职责分层：
 *  default 普通信息 / hero 核心结论 / section 信息模块 / flat 列表次级 / ai AI 辅助。
 * 不改任何业务逻辑，仅通过 variant 切换视觉权重。
 */
export default function Card({
  title,
  subtitle,
  action,
  hover,
  variant = "default",
  className = "",
  children,
}: CardProps) {
  const variantClass = variant === "default" ? "" : `card--${variant}`;
  return (
    <section className={`card ${variantClass} ${hover ? "card--hover" : ""} ${className}`}>
      {(title || action) && (
        <div className="card-header">
          <div>
            {title && <div className="card-title">{title}</div>}
            {subtitle && <div className="card-subtitle">{subtitle}</div>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
