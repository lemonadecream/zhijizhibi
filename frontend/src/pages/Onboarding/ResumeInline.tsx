import { useState } from "react";
import { api, type F1Parsed } from "../../api/client";
import ResumeUploader from "../../components/ResumeUploader";
import FreeTextInput from "../../components/FreeTextInput";
import DraftConfirm from "../../components/DraftConfirm";
import LoadingState from "../../components/ui/LoadingState";
import { useToast } from "../../components/ui/Toast";
import { useResumeParsePolling } from "../../hooks/usePolling";

export type ResumeEntryMode = "upload" | "paste" | "scratch";

interface Props {
  mode: ResumeEntryMode;
  onConfirmed: (resumeId: number | null) => void;
  onCancel: () => void;
}

type Sub = "form" | "parsing" | "confirm";

// 内联经历录入浮层（出现在对话区顶部，而非独立中间页）。
// 复用现有 F1 组件与接口，确认后回调，由 index 注入 AI 开场并进入访谈。
export default function ResumeInline({ mode, onConfirmed, onCancel }: Props) {
  const toast = useToast();
  const [sub, setSub] = useState<Sub>("form");
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [parsed, setParsed] = useState<F1Parsed | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { start: startPolling } = useResumeParsePolling({
    onParsed: (p) => {
      setParsed(p);
      setSub("confirm");
    },
    onFailed: (msg) => {
      setError(msg);
      setSub("form");
    },
  });

  const handleCreated = (id: number) => {
    setResumeId(id);
    setError(null);
    setSub("parsing");
    startPolling(id);
  };

  const handleConfirm = (draft: F1Parsed) => {
    if (resumeId === null) return;
    api
      .confirmResume(resumeId, draft)
      .then(() => onConfirmed(resumeId))
      .catch((e) => {
        setError(e?.message ?? "确认失败");
        toast.error(e?.message ?? "确认失败");
      });
  };

  return (
    <div className="onb-inline">
      <div className="onb-inline-head">
        <span className="onb-inline-title">
          {mode === "upload" ? "上传简历" : mode === "paste" ? "粘贴简历" : "从零开始"}
        </span>
        <button className="onb-inline-close" onClick={onCancel} aria-label="取消">
          ×
        </button>
      </div>
      {error && <div className="notice notice--error">{error}</div>}
      {sub === "form" &&
        (mode === "upload" ? (
          <ResumeUploader onUploaded={handleCreated} />
        ) : (
          <FreeTextInput onParsed={handleCreated} />
        ))}
      {sub === "parsing" && (
        <LoadingState
          label="AI 正在读取你的简历…"
          stages={["读取文件内容…", "抽取教育与经历…", "整理为结构化草稿…"]}
        />
      )}
      {sub === "confirm" && parsed && (
        <DraftConfirm parsed={parsed} onConfirm={handleConfirm} onCancel={() => setSub("form")} />
      )}
    </div>
  );
}
