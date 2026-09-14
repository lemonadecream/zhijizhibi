import { useState } from "react";
import { api, type F1Parsed } from "../../api/client";
import FreeTextInput from "../../components/FreeTextInput";
import DraftConfirm from "../../components/DraftConfirm";
import LoadingState from "../../components/ui/LoadingState";
import { useResumeParsePolling } from "../../hooks/usePolling";

interface Props {
  onConfirmed: () => void;
  onBack: () => void;
}

type Sub = "form" | "parsing" | "confirm";

// 从零开始:只收集一段最必要的经历描述即可,其余交给 AI 在访谈中补全。
export default function ScratchInput({ onConfirmed, onBack }: Props) {
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

  // FreeTextInput 的 onParsed 给出 resume id;我们在此接管轮询。
  const handleParsed = (id: number) => {
    setResumeId(id);
    setError(null);
    setSub("parsing");
    startPolling(id);
  };

  const handleConfirm = (draft: F1Parsed) => {
    if (resumeId === null) return;
    api
      .confirmResume(resumeId, draft)
      .then(() => onConfirmed())
      .catch((e) => setError(e?.message ?? "确认失败"));
  };

  return (
    <div className="onb-panel">
      <div className="onb-panel-head">
        <button className="onb-back" onClick={onBack}>
          ← 返回
        </button>
        <h2>从零开始</h2>
      </div>
      <p className="onb-panel-sub">
        先用一两句话告诉我你做过什么、喜欢什么就行。剩下的,我们边聊边补。
      </p>

      {error && <div className="notice notice--error">{error}</div>}

      {sub === "form" && <FreeTextInput onParsed={handleParsed} />}
      {sub === "parsing" && (
        <LoadingState
          label="AI 正在读取你的描述…"
          stages={["阅读你的描述…", "识别关键经历…", "整理为结构化草稿…"]}
        />
      )}
      {sub === "confirm" && parsed && <DraftConfirm parsed={parsed} onConfirm={handleConfirm} onCancel={() => setSub("form")} />}
    </div>
  );
}
