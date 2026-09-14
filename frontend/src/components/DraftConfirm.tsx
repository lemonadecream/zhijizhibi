import { useState } from "react";
import type { F1Parsed } from "../api/client";
import AIResultBlock from "./ai/AIResultBlock";
import Card from "./ui/Card";
import Input from "./ui/Input";
import Button from "./ui/Button";
import Tag from "./ui/Tag";

interface DraftConfirmProps {
  parsed: F1Parsed;
  onConfirm: (parsed: F1Parsed) => void;
  onCancel: () => void;
}

// F1 草稿确认:AI 提取结果以草稿呈现,用户核对、修改后确认才生效。
// 这是"AI 提供草稿、用户拥有最终记录"的人机协作关键环节。
export default function DraftConfirm({ parsed, onConfirm, onCancel }: DraftConfirmProps) {
  const [draft, setDraft] = useState<F1Parsed>(parsed);

  const setList = <K extends keyof F1Parsed>(key: K, value: F1Parsed[K]) => {
    setDraft((d) => ({ ...d, [key]: value }));
  };

  return (
    <AIResultBlock
      title="AI 已从你的简历 / 文本中提取以下内容,请核对后确认"
      onRegenerate={onCancel}
    >
      <div className="col" style={{ gap: 14 }}>
        <Card title="教育经历">
          {draft.education.length === 0 && <div className="muted" style={{ fontSize: "var(--text-sm)" }}>未识别到教育经历</div>}
          {draft.education.map((e, i) => (
            <div className="row" key={`e${i}`} style={{ marginBottom: 8 }}>
              <Input value={e.school} onChange={(v) => edit(draft, setList, "education", i, "school", v.target.value)} placeholder="学校" />
              <Input value={e.major} onChange={(v) => edit(draft, setList, "education", i, "major", v.target.value)} placeholder="专业" />
              <Input value={e.degree ?? ""} onChange={(v) => edit(draft, setList, "education", i, "degree", v.target.value)} placeholder="学历" />
            </div>
          ))}
        </Card>

        <Card title="实习经历">
          {draft.internships.length === 0 && <div className="muted" style={{ fontSize: "var(--text-sm)" }}>未识别到实习经历</div>}
          {draft.internships.map((e, i) => (
            <div className="row" key={`i${i}`} style={{ marginBottom: 8 }}>
              <Input value={e.company} onChange={(v) => edit(draft, setList, "internships", i, "company", v.target.value)} placeholder="公司" />
              <Input value={e.role} onChange={(v) => edit(draft, setList, "internships", i, "role", v.target.value)} placeholder="岗位" />
            </div>
          ))}
        </Card>

        <Card title="项目经历">
          {draft.projects.length === 0 && <div className="muted" style={{ fontSize: "var(--text-sm)" }}>未识别到项目经历</div>}
          {draft.projects.map((e, i) => (
            <div className="row" key={`p${i}`} style={{ marginBottom: 8 }}>
              <Input value={e.name} onChange={(v) => edit(draft, setList, "projects", i, "name", v.target.value)} placeholder="项目名称" />
              <Input value={e.role ?? ""} onChange={(v) => edit(draft, setList, "projects", i, "role", v.target.value)} placeholder="角色" />
            </div>
          ))}
        </Card>

        {(draft.skills.length > 0 || draft.interests.length > 0) && (
          <Card title="技能与兴趣">
            <div className="chips">
              {draft.skills.map((s, i) => (
                <Tag key={`s${i}`} tone="blue">{s.name}{s.level ? ` L${s.level}` : ""}</Tag>
              ))}
              {draft.interests.map((t, i) => (
                <Tag key={`t${i}`} tone="gray">{t}</Tag>
              ))}
            </div>
          </Card>
        )}

        <div className="actions">
          <Button variant="ghost" onClick={onCancel} type="button">
            重新录入
          </Button>
          <Button icon="check" onClick={() => onConfirm(draft)} type="button">
            确认并提交
          </Button>
        </div>
      </div>
    </AIResultBlock>
  );
}

function edit(
  draft: F1Parsed,
  setList: <K extends keyof F1Parsed>(key: K, value: F1Parsed[K]) => void,
  key: "education" | "internships" | "projects",
  i: number,
  field: string,
  val: string
) {
  const list = (draft[key] as unknown as Record<string, unknown>[]).slice();
  list[i] = { ...list[i]!, [field]: val };
  setList(key, list as unknown as F1Parsed[typeof key]);
}
