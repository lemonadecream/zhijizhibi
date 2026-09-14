import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Button from "../components/ui/Button";
import BrandMark from "../components/ui/BrandMark";
import Icon from "../components/ui/Icon";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await register({ email: email.trim() || undefined, password });
      // 新用户首次进入 -> /onboarding（沉浸式 AI 访谈）
      const s = await api.getOnboardingSession();
      navigate(s.status === "finalized" ? "/profile" : "/onboarding");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "注册失败");
    } finally {
      setBusy(false);
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
          注册后第一件事，是一次 10 分钟的 AI 访谈——
          它会认识你，然后陪您走完整个求职季。
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
          <p className="auth-subtitle">创建账号，开始建立你的职业画像。</p>

          <form onSubmit={submit} className="auth-form">
            <Input
              label="邮箱"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
            <Input
              label="密码(至少 6 位)"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              minLength={6}
              required
            />
            {error && <div className="notice notice--error">{error}</div>}
            <Button type="submit" loading={busy} block>
              {busy ? "注册中…" : "注册"}
            </Button>
          </form>

          <p className="auth-switch">
            已有账号?<Link to="/login">登录</Link>
          </p>
        </Card>
      </section>
    </div>
  );
}
