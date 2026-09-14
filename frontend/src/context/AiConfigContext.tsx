import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useAuth } from "./AuthContext";
import { api } from "../api/client";

/** Result of the read-only /api/config endpoint (P0-1). */
interface AiConfig {
  aiProvider: string; // "openai" | "mock" | other real provider name
  aiAvailable: boolean; // true only when a real, keyed provider is configured
  loaded: boolean;
}

const DEFAULT: AiConfig = { aiProvider: "openai", aiAvailable: false, loaded: false };

const AiConfigCtx = createContext<AiConfig>(DEFAULT);

export function AiConfigProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [cfg, setCfg] = useState<AiConfig>(DEFAULT);

  useEffect(() => {
    if (!token) {
      setCfg(DEFAULT);
      return;
    }
    let cancelled = false;
    api
      .getConfig()
      .then((c) => {
        if (!cancelled) setCfg({ aiProvider: c.ai_provider, aiAvailable: c.ai_available, loaded: true });
      })
      .catch(() => {
        if (!cancelled) setCfg((p) => ({ ...p, loaded: true }));
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return <AiConfigCtx.Provider value={cfg}>{children}</AiConfigCtx.Provider>;
}

export function useAiConfig(): AiConfig {
  return useContext(AiConfigCtx);
}
