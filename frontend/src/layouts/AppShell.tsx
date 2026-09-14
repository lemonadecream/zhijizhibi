import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import BrandMark from "../components/ui/BrandMark";
import Icon, { type IconName } from "../components/ui/Icon";

interface NavEntry {
  to: string;
  label: string;
  icon: IconName;
}

const NAV_ITEMS: NavEntry[] = [
  { to: "/profile", label: "职业画像", icon: "profile" },
  { to: "/explore", label: "职业探索", icon: "explore" },
  { to: "/target-job", label: "目标岗位", icon: "target" },
  { to: "/prepare", label: "求职准备", icon: "prepare" },
  { to: "/tracking", label: "求职追踪", icon: "tracking" },
  { to: "/offer", label: "Offer 决策", icon: "offer" },
];

function NavItems({ onClick }: { onClick?: () => void }) {
  return (
    <>
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          onClick={onClick}
          className={({ isActive }) => `nav-item ${isActive ? "nav-item--active" : ""}`}
        >
          <span className="nav-icon">
            <Icon name={item.icon} size={18} />
          </span>
          <span className="nav-label">{item.label}</span>
        </NavLink>
      ))}
    </>
  );
}

export default function AppShell() {
  const { email, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const currentLabel = NAV_ITEMS.find((n) => location.pathname.startsWith(n.to))?.label ?? "工作区";

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="shell">
      {/* Desktop / 平板侧边栏 */}
      <aside className="shell-sidebar">
        <div className="shell-brand">
          <BrandMark size={26} />
          <span className="brand-text">职己职彼</span>
        </div>
        <nav className="shell-nav">
          <div className="nav-section-label">工作区</div>
          <NavItems />
        </nav>
        <div className="shell-user">
          <Icon name="user" size={16} />
          <span className="user-email">{email ?? "未登录"}</span>
          <button className="icon-btn" onClick={handleLogout} title="退出登录" aria-label="退出登录">
            <Icon name="logout" size={16} />
          </button>
        </div>
      </aside>

      {/* 移动端顶部栏 */}
      <header className="shell-mobile-topbar">
        <BrandMark size={26} />
        <span className="brand-text" style={{ fontWeight: 600 }}>职己职彼</span>
        <span className="spacer" />
        <button className="icon-btn" onClick={handleLogout} aria-label="退出登录">
          <Icon name="logout" size={16} />
        </button>
      </header>

      {/* 主内容区 */}
      <main className="shell-main">
        <div className="shell-topbar">
          <span className="topbar-breadcrumb">{currentLabel}</span>
          <span className="topbar-spacer" />
          <span className="muted" style={{ fontSize: "var(--text-xs)" }}>{email}</span>
        </div>
        <div className="shell-content">
          <Outlet />
        </div>
      </main>

      {/* 移动端底部导航 */}
      <nav className="shell-bottom-nav">
        <div className="bottom-nav-list">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `bottom-nav-item ${isActive ? "bottom-nav-item--active" : ""}`}
            >
              <Icon name={item.icon} size={20} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
