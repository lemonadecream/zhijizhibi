import { useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import Icon from "./ui/Icon";
import LoadingState from "./ui/LoadingState";

interface ResumeUploaderProps {
  onUploaded: (resumeId: number) => void;
}

// 简历上传(业务逻辑不变,视觉重构)。
export default function ResumeUploader({ onUploaded }: ResumeUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleFile = async (file: File) => {
    setError(null);
    setBusy(true);
    try {
      const res = await api.uploadResume(file);
      onUploaded(res.resume_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div
        className="dropzone"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const f = e.dataTransfer.files?.[0];
          if (f) void handleFile(f);
        }}
      >
        <span className="entry-icon" style={{ marginBottom: 8 }}>
          <Icon name="upload" size={22} />
        </span>
        <div style={{ fontWeight: 600 }}>点击或拖拽上传简历</div>
        <div className="muted" style={{ fontSize: "var(--text-xs)", marginTop: 2 }}>
          仅支持 PDF / DOCX,单文件 ≤ 10MB
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleFile(f);
        }}
      />
      {busy && <LoadingState inline label="上传中…" />}
      {error && <div className="notice notice--error mt-2">{error}</div>}
    </div>
  );
}
