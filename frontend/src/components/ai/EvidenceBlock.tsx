import Icon from "../ui/Icon";

interface EvidenceBlockProps {
  text: string;
  label?: string;
}

// 证据/依据块:引用用户输入原文片段,建立"AI 判断可溯源"的视觉表达。
export default function EvidenceBlock({ text, label = "依据" }: EvidenceBlockProps) {
  return (
    <div className="evidence-block">
      <span className="evidence-label">
        <Icon name="evidence" size={12} />
        {label}
      </span>
      <div>{text}</div>
    </div>
  );
}
