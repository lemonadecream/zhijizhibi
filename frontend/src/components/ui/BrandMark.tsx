import Icon from "./Icon";

interface BrandMarkProps {
  /** 边长（px） */
  size?: number;
  /** 显示图标而不是文字 */
  icon?: "sparkles";
  className?: string;
}

// 品牌标识：蓝→紫渐变圆角块（呼应「职己职彼 = 知己知彼」的双色语言——
// 品牌蓝管行动、AI 紫管智能，Logo 是两者交汇的地方）。
// AppShell / 登录注册 / Onboarding 顶栏统一使用本组件。
export default function BrandMark({ size = 28, icon, className = "" }: BrandMarkProps) {
  return (
    <span
      className={`brand-mark ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.46) }}
      aria-hidden
    >
      {icon ? <Icon name={icon} size={Math.round(size * 0.52)} /> : "职"}
    </span>
  );
}
