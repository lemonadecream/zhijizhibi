import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type { F1Parsed, ProfileOut } from "../../api/client";
import Button from "../../components/ui/Button";
import LoadingState from "../../components/ui/LoadingState";
import ResumeUploader from "../../components/ResumeUploader";
import FreeTextInput from "../../components/FreeTextInput";
import ManualExperienceForm from "../../components/ManualExperienceForm";
import DraftConfirm from "../../components/DraftConfirm";
import ProfileView from "../../components/ProfileView";
import ProfileHome, { type EntryMode } from "../../components/ProfileHome";
import { usePolling, useResumeParsePolling } from "../../hooks/usePolling";

type View = "loading" | "entry" | "parsing" | "confirm" | "generating" | "profile";

// 职业画像工作区(Phase 1)。业务逻辑与 Phase 1 验收版完全一致,
// 本轮仅重构页面结构与视觉。
export default function ProfilePage() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>("loading");
  const [entryMode, setEntryMode] = useState<EntryMode | null>(null);
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [parsed, setParsed] = useState<F1Parsed | null>(null);
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 简历解析轮询（统一 hook，90s 上限）
  const { start: startResumePolling } = useResumeParsePolling({
    onParsed: (p) => {
      setParsed(p);
      setView("confirm");
    },
    onFailed: (msg) => {
      setError(msg);
      setView("entry");
    },
  });

  // 画像生成轮询：ready/edited 即完成；2 分钟上限后提示用户手动刷新
  const { start: startProfilePolling } = usePolling<ProfileOut>({
    fetch: () => api.getProfile(),
    decide: (p) => (p.status === "ready" || p.status === "edited" ? "done" : "continue"),
    onDone: (p) => {
      setProfile(p);
      setView("profile");
    },
    onGiveUp: (reason) => {
      if (reason === "max-attempts") {
        setError("画像生成时间较长，请稍后刷新页面查看结果。");
        setView("entry");
      }
    },
    maxAttempts: 120,
  });

  // 首次进入:加载已有画像。
  useEffect(() => {
    let active = true;
    api
      .getProfile()
      .then((p) => {
        if (!active) return;
        if (p.status && p.status !== "generating") {
          setProfile(p);
          setView("profile");
        } else if (p.status === "generating") {
          setView("generating");
          startProfilePolling();
        } else {
          setView("entry");
        }
      })
      .catch(() => {
        if (active) setView("entry");
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleResumeCreated = (id: number) => {
    setResumeId(id);
    setError(null);
    setView("parsing");
    startResumePolling(id);
  };

  const handleManualSaved = () => {
    setError(null);
    setEntryMode(null);
    setView("generating");
    api
      .generateProfile({})
      .then(() => startProfilePolling())
      .catch((e) => setError(e?.message ?? "生成失败"));
  };

  const handleConfirmDraft = (draft: F1Parsed) => {
    if (resumeId === null) return;
    setError(null);
    api
      .confirmResume(resumeId, draft)
      .then(() => {
        setView("generating");
        return api.generateProfile({});
      })
      .then(() => startProfilePolling())
      .catch((e) => setError(e?.message ?? "确认失败"));
  };

  const restart = () => {
    setParsed(null);
    setResumeId(null);
    setEntryMode(null);
    setError(null);
    setView("entry");
  };

  const renderEntryForm = () => {
    if (entryMode === "upload") return <ResumeUploader onUploaded={handleResumeCreated} />;
    if (entryMode === "text") return <FreeTextInput onParsed={handleResumeCreated} />;
    if (entryMode === "manual") return <ManualExperienceForm onSaved={handleManualSaved} />;
    return null;
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>职业画像</h1>
        <p className="page-desc">
          你的职业画像是后续职业探索、岗位匹配与求职准备的共同基础。先完善经历,AI 会帮你生成可追溯的能力画像。
        </p>
      </div>

      {error && <div className="notice notice--error">{error}</div>}

      {view === "loading" && <LoadingState label="加载中…" />}

      {view === "entry" && (
        <ProfileHome
          mode={entryMode}
          onSelect={setEntryMode}
          onResumeInterview={() => navigate("/onboarding")}
        >
          {renderEntryForm()}
        </ProfileHome>
      )}

      {view === "parsing" && <LoadingState label="正在解析你的简历…" />}

      {view === "confirm" && parsed && (
        <DraftConfirm parsed={parsed} onConfirm={handleConfirmDraft} onCancel={restart} />
      )}

      {view === "generating" && (
        <LoadingState
          label="AI 正在生成你的职业画像…"
          stages={["正在汇总你的经历…", "提炼能力与兴趣…", "生成可溯源的画像…"]}
        />
      )}

      {view === "profile" && profile && (
        <div>
          <ProfileView profile={profile} onUpdated={setProfile} />
          <section className="section">
            <h2 className="section-title">完善你的经历</h2>
            <ProfileHome
              mode={entryMode}
              onSelect={setEntryMode}
              progress={60}
              progressLabel="经历完整度"
            >
              {renderEntryForm()}
            </ProfileHome>
          </section>
          <section className="next-step">
            <div className="next-step__text">
              <div className="next-step__title">下一步：去职业探索</div>
              <div className="next-step__desc">
                画像已经就绪。接下来可以基于这份画像，看看有哪些职业方向值得你深入探索。
              </div>
            </div>
            <Button variant="primary" icon="arrowRight" onClick={() => navigate("/explore")}>
              去职业探索
            </Button>
          </section>
        </div>
      )}
    </div>
  );
}
