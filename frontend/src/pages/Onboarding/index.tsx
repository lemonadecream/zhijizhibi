import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type OnboardingSession, type OnboardingStepResult } from "../../api/client";
import BrandMark from "../../components/ui/BrandMark";
import { useToast } from "../../components/ui/Toast";
import WelcomeScreen from "./WelcomeScreen";
import InterviewChat from "./InterviewChat";
import CompletionConfirm from "./CompletionConfirm";
import type { ResumeEntryMode } from "./ResumeInline";

type Stage = "loading" | "welcome" | "interview" | "completion" | "finalizing" | "done";

export default function OnboardingPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [stage, setStage] = useState<Stage>("loading");
  const [session, setSession] = useState<OnboardingSession | null>(null);
  const [entryMode, setEntryMode] = useState<ResumeEntryMode | null>(null);

  // On mount: load existing session (so refresh resumes the interview).
  useEffect(() => {
    let active = true;
    api
      .getOnboardingSession()
      .then((s) => {
        if (!active) return;
        setSession(s);
        if (s.status === "finalized") {
          // 已完成画像：直接回到工作台，避免重复访谈
          navigate("/profile");
          return;
        }
        if (s.status === "completed") {
          setStage("completion");
        } else if (s.history.length > 0) {
          // 已有对话 -> 直接回到访谈（自动恢复进度）
          setStage("interview");
        } else {
          setStage("welcome");
        }
      })
      .catch(() => {
        if (active) setStage("welcome");
      });
    return () => {
      active = false;
    };
  }, [navigate]);

  // 用户任一入口确认后：bootstrap 会话（抓取已确认经历），进入访谈。
  const enterInterview = useCallback(
    (method: ResumeEntryMode, resumeId: number | null) => {
      setEntryMode(null);
      api
        .bootstrapOnboarding({ entry_method: method, resume_id: resumeId })
        .then((s) => {
          setSession(s);
          setStage("interview");
        })
        .catch((e) => toast.error(e?.message ?? "初始化访谈失败"));
    },
    [toast]
  );

  const handleEntryConfirmed = useCallback(
    (resumeId: number | null) => {
      // 入口模式：上传/粘贴走 "paste"，从零开始走 "scratch"
      const method: ResumeEntryMode = entryMode === "upload" ? "paste" : entryMode ?? "scratch";
      enterInterview(method, resumeId);
    },
    [entryMode, enterInterview]
  );

  const handleStep = useCallback(
    async (message: string): Promise<OnboardingStepResult> => {
      const res = await api.onboardingStep(message);
      setSession(res);
      return res;
    },
    []
  );

  // 流式访谈：增量渲染 AI 回复；最终结果与非流式同构，失败由 Chat 组件回退 onStep
  const handleStepStream = useCallback(
    (message: string, h: { onDelta(t: string): void; onDone(res: OnboardingStepResult): void; onError(m: string): void }) => {
      api.streamOnboardingStep(message, {
        onDelta: h.onDelta,
        onDone: (res) => {
          setSession(res);
          h.onDone(res);
        },
        onError: h.onError,
      });
    },
    []
  );

  const handleCorrect = useCallback(async (dimension: string, from_text: string, to_text: string) => {
    const s = await api.onboardingCorrect({ dimension, from_text, to_text });
    setSession(s);
  }, []);

  const handleFinalize = useCallback(async () => {
    setStage("finalizing");
    try {
      await api.onboardingFinalize();
      setStage("done");
      toast.success("你的职业画像已生成");
      setTimeout(() => navigate("/profile"), 700);
    } catch (e) {
      setStage("completion");
      toast.error(e instanceof Error ? e.message : "生成画像失败");
    }
  }, [navigate, toast]);

  const handleExit = useCallback(() => {
    // 稍后再说：访谈进度保存在服务端，随时可回 /onboarding 续聊（画像页有入口）。
    // 未定稿也去 /profile 而不是 /login——登录态下 /login 会重定向回 /onboarding，
    // 把用户弹回原点形成死循环；画像工作区有自己的录入流程，未定稿时同样可用。
    if (session?.status !== "finalized") {
      toast.success("访谈进度已保存，可随时回来继续");
    }
    navigate("/profile");
  }, [navigate, session, toast]);

  if (stage === "loading") {
    return <div className="onb-loading">正在准备你的专属陪伴…</div>;
  }
  if (stage === "done") {
    return (
      <div className="onb-done">
        <div className="onb-done-card">
          <h2>你的职业画像已经准备好了</h2>
          <p>接下来我会基于它，陪你一起探索适合的方向。</p>
          <button className="btn btn--primary btn--lg" onClick={() => navigate("/profile")}>
            查看我的职业画像
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="onb-root">
      {stage === "welcome" && (
        <WelcomeScreen
          onStart={() => {
            // 直接进入访谈（AI 开场白由后端 history 注入），入口在输入框旁
            setStage("interview");
          }}
        />
      )}

      {stage === "interview" && (
        <InterviewChat
          session={session}
          onStep={handleStep}
          onStepStream={handleStepStream}
          onCorrect={handleCorrect}
          onComplete={() => setStage("completion")}
          onExit={handleExit}
          onOpenEntry={(m) => setEntryMode(m)}
          entryMode={entryMode}
          onEntryConfirmed={handleEntryConfirmed}
          onEntryCancel={() => setEntryMode(null)}
        />
      )}

      {stage === "completion" && (
        <div className="onb-chat">
          <header className="onb-topbar">
            <div className="onb-topbar-brand">
              <BrandMark size={28} />
              职己职彼
            </div>
            <button className="onb-topbar-exit" onClick={handleExit}>
              稍后再说
            </button>
          </header>
          <main className="onb-chat-main">
            <div className="onb-chat-scroll">
              <CompletionConfirm session={session} onFinalize={handleFinalize} onBack={() => setStage("interview")} />
            </div>
          </main>
          <aside className="onb-aside" />
        </div>
      )}

      {stage === "finalizing" && <div className="onb-loading">AI 正在生成你的职业画像…</div>}
    </div>
  );
}
