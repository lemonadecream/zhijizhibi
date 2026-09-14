import { useState } from "react";
import { api, type F1Parsed } from "../../api/client";
import ResumeUploader from "../../components/ResumeUploader";
import FreeTextInput from "../../components/FreeTextInput";
import DraftConfirm from "../../components/DraftConfirm";
import LoadingState from "../../components/ui/LoadingState";
import { useResumeParsePolling } from "../../hooks/usePolling";

interface Props {
  mode: "upload" | "paste" | "scratch";
  onConfirmed: (resumeId: number) => void;
  onBack: () => void;
}

type Sub = "form" | "parsing" | "confirm";

export default function ResumeFlow({ mode, onConfirmed, onBack }: Props) {
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
      .catch((e) => setError(e?.message ?? "确认失败"));
  };

  return (
    <div className="onb-panel">
      <div className="onb-panel-head">
        <button className="onb-back" onClick={onBack}>
          ← 返回
        </button>
        <h2>{mode === "upload" ? "上传简历" : "粘贴简历"}</h2>
      </div>

      {error && <div className="notice notice--error">{error}</div>}

      {sub === "form" && (mode === "upload" ? <ResumeUploader onUploaded={handleCreated} /> : <FreeTextInput onParsed={handleCreated} />)}

      {sub === "parsing" && (
        <LoadingState
          label="AI 正在读取你的简历…"
          stages={["读取文件内容…", "抽取教育与经历…", "整理为结构化草稿…"]}
        />
      )}

      {sub === "confirm" && parsed && <DraftConfirm parsed={parsed} onConfirm={handleConfirm} onCancel={() => setSub("form")} />}
    </div>
  );
}
