import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { ExperienceInput } from "../api/client";
import Card from "./ui/Card";
import Input from "./ui/Input";
import Button from "./ui/Button";

type Edu = { school: string; major: string; degree: string; start: string; end: string };
type Intern = { company: string; role: string; start: string; end: string; duty: string };
type Project = { name: string; role: string; desc: string };
type Skill = { name: string; level: string };

const emptyEdu: Edu = { school: "", major: "", degree: "", start: "", end: "" };
const emptyIntern: Intern = { company: "", role: "", start: "", end: "", duty: "" };
const emptyProject: Project = { name: "", role: "", desc: "" };
const emptySkill: Skill = { name: "", level: "" };

interface ManualExperienceFormProps {
  onSaved: () => void;
}

// 手动录入经历(业务逻辑不变,视觉重构)。
export default function ManualExperienceForm({ onSaved }: ManualExperienceFormProps) {
  const [edus, setEdus] = useState<Edu[]>([{ ...emptyEdu }]);
  const [interns, setInterns] = useState<Intern[]>([{ ...emptyIntern }]);
  const [projects, setProjects] = useState<Project[]>([{ ...emptyProject }]);
  const [skills, setSkills] = useState<Skill[]>([{ ...emptySkill }]);
  const [interests, setInterests] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const payload: ExperienceInput = {
      education: edus.filter((x) => x.school || x.major).map((x) => ({ ...x })),
      internships: interns.filter((x) => x.company || x.role).map((x) => ({ ...x })),
      projects: projects.filter((x) => x.name).map((x) => ({ ...x })),
      skills: skills
        .filter((x) => x.name)
        .map((x) => ({ name: x.name, level: x.level ? Number(x.level) : undefined })),
      interests: interests
        .split(/[，,\n]/)
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      await api.saveManualExperience(payload);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="col" style={{ gap: 16 }}>
      <Card title="教育经历">
        {edus.map((e, i) => (
          <div className="row" key={`e${i}`} style={{ marginBottom: 8 }}>
            <Input placeholder="学校" value={e.school} onChange={(v) => update(setEdus, edus, i, "school", v.target.value)} />
            <Input placeholder="专业" value={e.major} onChange={(v) => update(setEdus, edus, i, "major", v.target.value)} />
            <Input placeholder="学历" value={e.degree} onChange={(v) => update(setEdus, edus, i, "degree", v.target.value)} />
            <Input placeholder="起(如2020-09)" value={e.start} onChange={(v) => update(setEdus, edus, i, "start", v.target.value)} />
            <Input placeholder="止" value={e.end} onChange={(v) => update(setEdus, edus, i, "end", v.target.value)} />
          </div>
        ))}
        <Button variant="ghost" size="sm" icon="plus" onClick={() => setEdus([...edus, { ...emptyEdu }])} type="button">
          添加教育
        </Button>
      </Card>

      <Card title="实习经历">
        {interns.map((e, i) => (
          <div className="row" key={`i${i}`} style={{ marginBottom: 8 }}>
            <Input placeholder="公司" value={e.company} onChange={(v) => update(setInterns, interns, i, "company", v.target.value)} />
            <Input placeholder="岗位" value={e.role} onChange={(v) => update(setInterns, interns, i, "role", v.target.value)} />
            <Input placeholder="起" value={e.start} onChange={(v) => update(setInterns, interns, i, "start", v.target.value)} />
            <Input placeholder="止" value={e.end} onChange={(v) => update(setInterns, interns, i, "end", v.target.value)} />
            <Input placeholder="职责" value={e.duty} onChange={(v) => update(setInterns, interns, i, "duty", v.target.value)} />
          </div>
        ))}
        <Button variant="ghost" size="sm" icon="plus" onClick={() => setInterns([...interns, { ...emptyIntern }])} type="button">
          添加实习
        </Button>
      </Card>

      <Card title="项目经历">
        {projects.map((e, i) => (
          <div className="row" key={`p${i}`} style={{ marginBottom: 8 }}>
            <Input placeholder="项目名称" value={e.name} onChange={(v) => update(setProjects, projects, i, "name", v.target.value)} />
            <Input placeholder="角色" value={e.role} onChange={(v) => update(setProjects, projects, i, "role", v.target.value)} />
            <Input placeholder="描述" value={e.desc} onChange={(v) => update(setProjects, projects, i, "desc", v.target.value)} />
          </div>
        ))}
        <Button variant="ghost" size="sm" icon="plus" onClick={() => setProjects([...projects, { ...emptyProject }])} type="button">
          添加项目
        </Button>
      </Card>

      <Card title="技能">
        {skills.map((e, i) => (
          <div className="row" key={`s${i}`} style={{ marginBottom: 8 }}>
            <Input placeholder="技能名" value={e.name} onChange={(v) => update(setSkills, skills, i, "name", v.target.value)} />
            <Input placeholder="熟练度 1-5" value={e.level} onChange={(v) => update(setSkills, skills, i, "level", v.target.value)} />
          </div>
        ))}
        <Button variant="ghost" size="sm" icon="plus" onClick={() => setSkills([...skills, { ...emptySkill }])} type="button">
          添加技能
        </Button>
      </Card>

      <Card title="兴趣">
        <Input
          placeholder="用逗号分隔,例如:后端开发,数据分析"
          value={interests}
          onChange={(v) => setInterests(v.target.value)}
        />
      </Card>

      {error && <div className="notice notice--error">{error}</div>}
      <div>
        <Button type="submit" loading={busy} icon="check">
          {busy ? "保存中…" : "保存并生成画像"}
        </Button>
      </div>
    </form>
  );
}

function update<T>(setter: (v: T[]) => void, list: T[], i: number, key: keyof T, val: string) {
  const next = list.slice();
  next[i] = { ...next[i]!, [key]: val };
  setter(next);
}
