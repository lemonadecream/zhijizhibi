import { useState } from "react";
import { ApiError, api } from "../api/client";
import Textarea from "./ui/Textarea";
import Button from "./ui/Button";

interface FreeTextInputProps {
  onParsed: (resumeId: number) => void;
}

// 粘贴经历文本(业务逻辑不变,视觉重构)。
export default function FreeTextInput({ onParsed }: FreeTextInputProps) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api.parseText(text);
      onParsed(res.resume_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="col" style={{ gap: 14 }}>
      <Textarea
        label="粘贴你的经历描述"
        hint="至少 10 个字。例如:我就读于某大学计算机专业,曾在某公司实习担任后端开发……"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="描述你的教育、实习、项目经历,以及你感兴趣的方向…"
        rows={8}
      />
      {error && <div className="notice notice--error">{error}</div>}
      <div>
        <Button type="submit" loading={busy} disabled={text.trim().length < 10} icon="sparkle">
          {busy ? "解析中…" : "提交并解析"}
        </Button>
      </div>
    </form>
  );
}
