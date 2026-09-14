/**
 * 手绘 SVG 插画库（P3-V3 视觉升级）。
 *
 * 设计约定：
 *  - 统一风格：圆角几何 + 品牌渐变填充 + 细线描边，与 tokens 双色语言一致；
 *  - 尺寸：viewBox 120×120，容器自适应；
 *  - 渐变 id 全局唯一前缀（ill-），避免多实例冲突；
 *  - 只用于空态/英雄区等大面积场景，禁止塞进 16px 图标位。
 *
 * 这是"图画"能力的生产级实现：矢量、随主题换色、零额外请求——
 * 比位图插画更适合进设计系统。
 */

export function IllustrationExplore() {
  return (
    <svg viewBox="0 0 120 120" width="100%" height="100%" aria-hidden>
      <defs>
        <linearGradient id="ill-a" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b6ef9" />
          <stop offset="1" stopColor="#b46ef0" />
        </linearGradient>
      </defs>
      <circle cx="60" cy="60" r="44" fill="#f6f4fe" />
      <circle cx="60" cy="60" r="44" fill="none" stroke="#e6e0fb" strokeWidth="2" />
      <circle cx="60" cy="60" r="32" fill="none" stroke="url(#ill-a)" strokeWidth="2.5" strokeDasharray="4 6" opacity="0.5" />
      <path d="M78 42 L54 54 L42 78 L66 66 Z" fill="url(#ill-a)" opacity="0.9" />
      <path d="M78 42 L54 54 L66 66 Z" fill="#ffffff" opacity="0.35" />
      <circle cx="60" cy="60" r="4" fill="#ffffff" stroke="url(#ill-a)" strokeWidth="2" />
      <circle cx="20" cy="30" r="3" fill="#3b6ef9" opacity="0.4" />
      <circle cx="100" cy="26" r="2.5" fill="#b46ef0" opacity="0.45" />
      <circle cx="102" cy="92" r="3.5" fill="#3b6ef9" opacity="0.3" />
      <circle cx="14" cy="88" r="2" fill="#b46ef0" opacity="0.4" />
    </svg>
  );
}

export function IllustrationTarget() {
  return (
    <svg viewBox="0 0 120 120" width="100%" height="100%" aria-hidden>
      <defs>
        <linearGradient id="ill-b" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b6ef9" />
          <stop offset="1" stopColor="#b46ef0" />
        </linearGradient>
      </defs>
      <rect x="14" y="26" width="92" height="72" rx="12" fill="#f6f4fe" stroke="#e6e0fb" strokeWidth="2" />
      <path
        d="M26 84 C40 84 40 62 56 62 C72 62 70 40 92 40"
        fill="none"
        stroke="url(#ill-b)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="1 7"
      />
      <circle cx="26" cy="84" r="5" fill="#ffffff" stroke="#3b6ef9" strokeWidth="2.5" />
      <path d="M92 28 c-7 0 -12 5.5 -12 12 c0 8.5 12 20 12 20 s12 -11.5 12 -20 c0 -6.5 -5 -12 -12 -12 Z" fill="url(#ill-b)" />
      <circle cx="92" cy="40" r="4.5" fill="#ffffff" />
    </svg>
  );
}

export function IllustrationPrepare() {
  return (
    <svg viewBox="0 0 120 120" width="100%" height="100%" aria-hidden>
      <defs>
        <linearGradient id="ill-c" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b6ef9" />
          <stop offset="1" stopColor="#b46ef0" />
        </linearGradient>
      </defs>
      <path d="M60 16 c14 12 20 30 20 48 l0 18 -40 0 0 -18 c0 -18 6 -36 20 -48 Z" fill="#f6f4fe" stroke="url(#ill-c)" strokeWidth="2.5" />
      <circle cx="60" cy="52" r="9" fill="#ffffff" stroke="#3b6ef9" strokeWidth="2.5" />
      <path d="M40 74 l-12 14 18 -2 Z" fill="url(#ill-c)" opacity="0.85" />
      <path d="M80 74 l12 14 -18 -2 Z" fill="url(#ill-c)" opacity="0.85" />
      <path d="M52 90 h16 l-3 12 h-10 Z" fill="url(#ill-c)" opacity="0.55" />
      <circle cx="96" cy="24" r="3" fill="#b46ef0" opacity="0.5" />
      <circle cx="22" cy="36" r="2.5" fill="#3b6ef9" opacity="0.4" />
      <path d="M14 62 l3 3 M20 56 l-3 3" stroke="#b46ef0" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
    </svg>
  );
}

export function IllustrationTracking() {
  return (
    <svg viewBox="0 0 120 120" width="100%" height="100%" aria-hidden>
      <defs>
        <linearGradient id="ill-d" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b6ef9" />
          <stop offset="1" stopColor="#b46ef0" />
        </linearGradient>
      </defs>
      <path d="M24 96 V30 c0 -8 6 -14 14 -14 h8" fill="none" stroke="#d8dde7" strokeWidth="3" strokeLinecap="round" />
      <path d="M46 16 h44 l-9 12 9 12 H46 Z" fill="url(#ill-d)" />
      <path d="M24 62 c18 -6 30 8 48 2 c10 -3 16 -8 22 -14" fill="none" stroke="url(#ill-d)" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="1 7" opacity="0.6" />
      <circle cx="24" cy="62" r="4.5" fill="#ffffff" stroke="#3b6ef9" strokeWidth="2.5" />
      <circle cx="94" cy="50" r="4" fill="#b46ef0" />
      <rect x="18" y="92" width="12" height="10" rx="3" fill="#e6e0fb" />
    </svg>
  );
}

export function IllustrationOffer() {
  return (
    <svg viewBox="0 0 120 120" width="100%" height="100%" aria-hidden>
      <defs>
        <linearGradient id="ill-e" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b6ef9" />
          <stop offset="1" stopColor="#b46ef0" />
        </linearGradient>
      </defs>
      <rect x="52" y="30" width="16" height="10" rx="5" fill="url(#ill-e)" />
      <path d="M60 40 V92" stroke="#d8dde7" strokeWidth="3" strokeLinecap="round" />
      <path d="M22 52 L60 40 L98 52" fill="none" stroke="url(#ill-e)" strokeWidth="3" strokeLinecap="round" />
      <path d="M22 52 L12 72 h20 Z" fill="#eef3ff" stroke="#3b6ef9" strokeWidth="2" />
      <path d="M98 52 L88 72 h20 Z" fill="#efe9fd" stroke="#b46ef0" strokeWidth="2" />
      <rect x="48" y="92" width="24" height="6" rx="3" fill="#d8dde7" />
      <circle cx="18" cy="26" r="2.5" fill="#3b6ef9" opacity="0.35" />
      <circle cx="102" cy="22" r="3" fill="#b46ef0" opacity="0.4" />
    </svg>
  );
}

export function IllustrationProfile() {
  return (
    <svg viewBox="0 0 120 120" width="100%" height="100%" aria-hidden>
      <defs>
        <linearGradient id="ill-f" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b6ef9" />
          <stop offset="1" stopColor="#b46ef0" />
        </linearGradient>
      </defs>
      <rect x="20" y="18" width="80" height="88" rx="14" fill="#f6f4fe" stroke="#e6e0fb" strokeWidth="2" />
      <path d="M20 32 c0 -8 6 -14 14 -14 h52 c8 0 14 6 14 14 v8 H20 Z" fill="url(#ill-f)" opacity="0.9" />
      <circle cx="46" cy="62" r="13" fill="#ffffff" stroke="url(#ill-f)" strokeWidth="2.5" />
      <path d="M46 55 a4 4 0 1 1 0 8 a4 4 0 1 1 0 -8 M38 72 c1 -5 4 -7 8 -7 s7 2 8 7" fill="none" stroke="#3b6ef9" strokeWidth="2" strokeLinecap="round" />
      <rect x="66" y="54" width="24" height="5" rx="2.5" fill="#c9d4f9" />
      <rect x="66" y="64" width="18" height="5" rx="2.5" fill="#e6e0fb" />
      <rect x="34" y="84" width="52" height="5" rx="2.5" fill="#e6e0fb" />
      <rect x="34" y="94" width="36" height="5" rx="2.5" fill="#efe9fd" />
    </svg>
  );
}

/** 英雄区极光背景：抽象光斑 + 星点 + 连线，绝对定位铺满容器使用。 */
export function AuroraBackdrop() {
  return (
    <svg
      viewBox="0 0 800 500"
      preserveAspectRatio="xMidYMid slice"
      width="100%"
      height="100%"
      aria-hidden
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    >
      <defs>
        <radialGradient id="au-1" cx="0.2" cy="0.15" r="0.6">
          <stop offset="0" stopColor="#6d4fd8" stopOpacity="0.14" />
          <stop offset="1" stopColor="#6d4fd8" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="au-2" cx="0.85" cy="0.8" r="0.6">
          <stop offset="0" stopColor="#3b6ef9" stopOpacity="0.12" />
          <stop offset="1" stopColor="#3b6ef9" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="au-line" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b6ef9" stopOpacity="0.25" />
          <stop offset="1" stopColor="#b46ef0" stopOpacity="0.25" />
        </linearGradient>
      </defs>
      <rect width="800" height="500" fill="url(#au-1)" />
      <rect width="800" height="500" fill="url(#au-2)" />
      <g stroke="url(#au-line)" strokeWidth="1.2">
        <path d="M90 120 L210 70 L330 130" fill="none" />
        <path d="M620 380 L700 300 L760 340" fill="none" />
      </g>
      <circle cx="90" cy="120" r="4" fill="#3b6ef9" opacity="0.35" />
      <circle cx="210" cy="70" r="3" fill="#b46ef0" opacity="0.4" />
      <circle cx="330" cy="130" r="2.5" fill="#3b6ef9" opacity="0.3" />
      <circle cx="620" cy="380" r="4" fill="#b46ef0" opacity="0.35" />
      <circle cx="700" cy="300" r="3" fill="#3b6ef9" opacity="0.35" />
      <circle cx="760" cy="340" r="2.5" fill="#b46ef0" opacity="0.3" />
    </svg>
  );
}
