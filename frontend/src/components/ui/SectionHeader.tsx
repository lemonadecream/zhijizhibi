import type { ReactNode } from "react";

interface SectionHeaderProps {
  title: ReactNode;
  sub?: ReactNode;
  action?: ReactNode;
  /** secondary：卡片内分组 / 列表子标题（无竖线、字号更小） */
  secondary?: boolean;
  /** 是否显示左侧品牌竖线（仅 primary 生效，默认显示） */
  bar?: boolean;
}

export default function SectionHeader({ title, sub, action, secondary, bar = true }: SectionHeaderProps) {
  return (
    <div className={`section-header ${secondary ? "section-header--secondary" : ""}`}>
      {!secondary && bar && <span className="section-header__bar" aria-hidden />}
      <div>
        <div className="section-header__title">{title}</div>
        {sub && <div className="section-header__sub">{sub}</div>}
      </div>
      {action && <div className="section-header__action">{action}</div>}
    </div>
  );
}
