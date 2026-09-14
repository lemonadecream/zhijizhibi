import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, clearToken, getToken, setToken } from "../api/client";

interface AuthState {
  token: string | null;
  userId: number | null;
  email: string | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  register: (input: { email?: string; phone?: string; password: string; name?: string }) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(getToken());
  const [userId, setUserId] = useState<number | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((m) => {
        setUserId(m.user_id);
        setEmail(m.email);
      })
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, [token]);

  // 会话失效广播（client.ts 在 401 时发出）：同步清空 React 状态，
  // 否则 RequireAuth 仍看到旧 token，用户被困在无限报错里。
  useEffect(() => {
    const onExpired = () => {
      setTok(null);
      setUserId(null);
      setEmail(null);
    };
    window.addEventListener("cdp:auth-expired", onExpired);
    return () => window.removeEventListener("cdp:auth-expired", onExpired);
  }, []);

  const login = async (identifier: string, password: string) => {
    const r = await api.login({ identifier, password });
    // 先持久化 token 供 me() 使用，但 React 状态等 me() 确认后才置为已登录；
    // me() 失败则回滚 localStorage，避免"页面报错但 token 已存"的不一致。
    setToken(r.access_token);
    try {
      const m = await api.me();
      setTok(r.access_token);
      setUserId(m.user_id);
      setEmail(m.email);
    } catch (e) {
      clearToken();
      throw e;
    }
  };

  const register = async (input: { email?: string; phone?: string; password: string; name?: string }) => {
    const r = await api.register(input);
    setToken(r.access_token);
    try {
      const m = await api.me();
      setTok(r.access_token);
      setUserId(m.user_id);
      setEmail(m.email);
    } catch (e) {
      clearToken();
      throw e;
    }
  };

  const logout = () => {
    clearToken();
    setTok(null);
    setUserId(null);
    setEmail(null);
  };

  return (
    <Ctx.Provider value={{ token, userId, email, loading, login, register, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used within AuthProvider");
  return c;
}
