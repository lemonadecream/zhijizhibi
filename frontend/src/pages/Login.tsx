import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Button from "../components/ui/Button";
import BrandMark from "../components/ui/BrandMark";
import Icon from "../components/ui/Icon";

// 「体验 Demo」入口使用的公开演示账号（数据全部为虚构，由 backend/app/db/seed_demo.py 生成）。
// 这里只是把凭据写死在按钮上，登录走的仍是**同一个** auth flow：
// AuthContext.login → api.login → POST /api/auth/login。没有 Demo 专属 Auth / API / 路由 / 权限。
const DEMO_IDENTIFIER = "demo@zhijizhibi.app";
const DEMO_PASSWORD = "demo123456";

// 认证页改版（P3 设计升级）：居中小卡 → 左品牌区 + 右表单分栏。
// 左侧承担"产品是什么"的一次性讲述（桌面端），移动端自动退化为单列表单。
export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(identifier.trim(), password);
      // 已完成画像 -> /profile；否则 -> /onboarding（自动恢复进度）
      const s = await api.getOnboardingSession();
      navigate(s.status === "finalized" ? "/profile" : "/onboarding");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败");
    } finally {
      setBusy(false);
    }
  };

  // Demo 入口：与上面的普通登录共用同一个 login()，只是凭据固定、落点固定为 /profile。
  // 演示账号的画像已生成，因此这里**不做** onboarding 判定，也不进 onboarding。
  const enterDemo = async () => {
    setError(null);
    setDemoBusy(true);
    try {
      await login(DEMO_IDENTIFIER, DEMO_PASSWORD);
      navigate("/profile");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "演示账号暂时不可用，请稍后重试");
    } finally {
      setDemoBusy(false);
    }
  };

  return (
    <div className="auth-split">
      <section className="auth-hero">
        <div className="auth-hero__brand">
          <BrandMark size={40} />
          <span>职己职彼</span>
        </div>
        <h1 className="auth-hero__title">
          懂职场，
          <br />
          也更懂自己。
        </h1>
        <p className="auth-hero__desc">
          从一次 AI 访谈开始，把你的经历、能力与偏好沉淀成一份可成长的职业画像——
          再陪你探索方向、判断岗位、追踪投递、比较 Offer。
        </p>
        <ul className="auth-hero__points">
          <li>
            <Icon name="check" size={15} />
            AI 访谈生成可溯源的职业画像，每个判断都有依据
          </li>
          <li>
            <Icon name="check" size={15} />
            JD 结构化解析 × 能力匹配 × Gap 补齐路线
          </li>
          <li>
            <Icon name="check" size={15} />
            多 Offer 加权对比——AI 只解释，决定权在你
          </li>
        </ul>
      </section>

      <section className="auth-panel">
        <Card className="auth-card">
          <div className="auth-brand">
            <BrandMark size={26} />
            职己职彼
          </div>
          <p className="auth-subtitle">欢迎回来，继续你的求职决策。</p>

          <form onSubmit={submit} className="auth-form">
            <Input
              label="邮箱或手机号"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="you@example.com"
              autoComplete="username"
              required
            />
            <Input
              label="密码"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            {error && <div className="notice notice--error">{error}</div>}
            <Button type="submit" loading={busy} disabled={demoBusy} block>
              {busy ? "登录中…" : "登录"}
            </Button>
          </form>

          <div className="auth-divider">
            <span>或</span>
          </div>

          <div className="auth-demo">
            <Button
              type="button"
              variant="secondary"
              block
              icon="sparkles"
              loading={demoBusy}
              disabled={busy}
              onClick={enterDemo}
            >
              {demoBusy ? "正在进入演示…" : "体验 Demo"}
            </Button>
            <p className="auth-demo__hint">无需注册 · 使用演示数据</p>
          </div>

          <p className="auth-switch">
            还没有账号?<Link to="/register">注册</Link>
          </p>
        </Card>
      </section>
    </div>
  );
}
