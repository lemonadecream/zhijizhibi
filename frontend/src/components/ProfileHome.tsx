import type { ReactNode } from "react";
import Card from "./ui/Card";
import Icon, { type IconName } from "./ui/Icon";
import Progress from "./ui/Progress";

export type EntryMode = "upload" | "text" | "manual";

const ENTRIES: { key: EntryMode; icon: IconName; title: string; desc: string }[] = [
  { key: "upload", icon: "upload", title: "上传简历", desc: "PDF / DOCX,AI 自动提取经历" },
  { key: "text", icon: "fileText", title: "粘贴经历文本", desc: "直接描述你的教育与实习经历" },
  { key: "manual", icon: "edit", title: "手动填写", desc: "自行逐项录入教育 / 实习 / 项目" },
];

interface ProfileHomeProps {
  mode: EntryMode | null;
  onSelect: (mode: EntryMode) => void;
  progress?: number;
  progressLabel?: string;
  /** 存在未完成的 AI 访谈（Onboarding）时展示"继续访谈"入口，形成离开/回来的闭环 */
  onResumeInterview?: () => void;
  children?: ReactNode;
}

// 画像录入入口:三种方式 + 完成度,是职业画像工作区的起点。
export default function ProfileHome({
  mode,
  onSelect,
  progress = 0,
  progressLabel = "画像完成度",
  onResumeInterview,
  children,
}: ProfileHomeProps) {
  return (
    <div>
      <Card className="completeness-card">
        <div>
          <div className="card-title">完善你的经历</div>
          <div className="card-subtitle">你的经历是 AI 生成职业画像的基础,三种方式可组合使用</div>
        </div>
        <div style={{ width: 180 }}>
          <Progress value={progress} label={progressLabel} showValue />
        </div>
      </Card>

      <div className="entry-cards">
        {ENTRIES.map((e) => (
          <button
            key={e.key}
            type="button"
            className={`entry-card ${mode === e.key ? "entry-card--active" : ""}`}
            onClick={() => onSelect(e.key)}
          >
            <span className="entry-icon">
              <Icon name={e.icon} size={20} />
            </span>
            <span className="entry-title">{e.title}</span>
            <span className="entry-desc">{e.desc}</span>
          </button>
        ))}
      </div>

      {onResumeInterview && (
        <button type="button" className="entry-card entry-card--wide" onClick={onResumeInterview}>
          <span className="entry-icon">
            <Icon name="sparkles" size={20} />
          </span>
          <span className="entry-title">继续 AI 访谈</span>
          <span className="entry-desc">接着上次的对话进度聊，AI 会引导你补全画像</span>
        </button>
      )}

      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}
