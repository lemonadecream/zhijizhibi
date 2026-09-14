import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { AbilityTag, ProfileOut, ProfileUpdate, Risk, TagWithEvidence } from "../api/client";
import AIResultBlock from "./ai/AIResultBlock";
import Card from "./ui/Card";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import Input from "./ui/Input";
import Tag from "./ui/Tag";

interface ProfileViewProps {
  profile: ProfileOut;
  onUpdated: (p: ProfileOut) => void;
}

interface Tendency {
  axis: string;
  leaning: number;
  confidence?: number;
  note?: string;
}

// 职业画像展示(Phase 1B 视觉重构):
// 从"后台表格"改为"属于用户自己的职业档案"——定位总结 / 能力地图 / 倾向 /
// 兴趣动机 / 优势 / 成长建议。AI 输出仍标注并可编辑。
export default function ProfileView({ profile, onUpdated }: ProfileViewProps) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Phase 1B 扩展字段收纳在 preference_infer 中(后端无独立列)。
  const extras = (profile.preference_infer ?? {}) as Record<string, unknown>;
  const positioning = typeof extras.positioning === "string" ? (extras.positioning as string) : "";
  const tendencies = Array.isArray(extras.tendencies) ? (extras.tendencies as Tendency[]) : [];
  const motivations = Array.isArray(extras.motivations) ? (extras.motivations as string[]) : [];
  const gapsRaw = Array.isArray(extras.gaps) ? (extras.gaps as { item: string; why: string; evidence?: string }[]) : [];
  const careerGoal = typeof extras.career_goal === "string" ? (extras.career_goal as string) : "";

  // 兼容旧数据:若无 positioning,则用首条 strength 兜底展示。
  const positioningText = positioning || (profile.strengths[0]?.item ?? "你的职业画像还在建设中。");

  const [draft, setDraft] = useState<ProfileUpdate>({
    ability_tags: profile.ability_tags,
    interest_tags: profile.interest_tags,
    strengths: profile.strengths,
    risks: profile.risks,
    preference_infer: profile.preference_infer,
  });

  const save = async () => {
    setError(null);
    setBusy(true);
    try {
      const pref = { ...draft.preference_infer };
      delete (pref as Record<string, unknown>)["_ai_failed"];
      await api.updateProfile({ ...draft, preference_infer: pref });
      const updated = await api.getProfile();
      onUpdated(updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const statusTone = profile.status === "edited" ? "blue" : profile.status === "ready" ? "green" : "neutral";

  return (
    <div className="pv">
      {/* 顶部:定位总结 */}
      <section className="pv-hero">
        <div className="pv-hero-head">
          <h2 className="pv-hero-title">你的职业画像</h2>
          <div className="row" style={{ gap: 8 }}>
            <Badge tone={statusTone}>{profile.status === "edited" ? "已编辑" : "AI 生成"}</Badge>
            <Badge tone="neutral">v{profile.version ?? 1}</Badge>
            {!editing && (
              <Button variant="secondary" size="sm" icon="edit" onClick={() => setEditing(true)}>
                编辑
              </Button>
            )}
          </div>
        </div>
        <span className="hero-eyebrow" style={{ marginBottom: 12 }}>AI 给你的定位</span>
        <p className="pv-positioning">{positioningText}</p>
        {careerGoal && (
          <p className="pv-goal">求职意向：{careerGoal}</p>
        )}
      </section>

      {profile.ai_failed && !editing && (
        <div className="notice notice--warning" style={{ marginBottom: 14 }}>
          AI 生成暂未成功,已为你保留空白画像。点击「编辑」手动填写你的画像内容。
        </div>
      )}
      {error && <div className="notice notice--error" style={{ marginBottom: 14 }}>{error}</div>}

      {!editing && (
        <>
          {/* 能力地图 */}
          <section className="pv-section">
            <h3 className="pv-section-title">能力地图</h3>
            {profile.ability_tags.length === 0 ? (
              <div className="pv-hint">我还需要了解你更多（暂无能力标签）</div>
            ) : (
              <div className="pv-bubbles">
                {profile.ability_tags.map((t: AbilityTag, i) => (
                  <span key={`a${i}`} className={`pv-bubble pv-bubble--${bubbleSize(t.level)}`}>
                    {t.tag}
                    {t.level ? <em>L{t.level}</em> : null}
                  </span>
                ))}
              </div>
            )}
          </section>

          {/* 职业倾向 */}
          <section className="pv-section">
            <h3 className="pv-section-title pv-section-title--secondary">你的职业倾向</h3>
            {tendencies.length === 0 ? (
              <div className="pv-hint">我还需要了解你更多（暂无倾向数据）</div>
            ) : (
              <div className="pv-tendencies">
                {tendencies.map((t, i) => (
                  <div className="pv-tendency" key={`t${i}`}>
                    <span className="pv-tendency-label">{t.axis}</span>
                    <span className="pv-tendency-track">
                      <span className="pv-tendency-fill" style={{ width: `${Math.round((t.leaning ?? 0.5) * 100)}%` }} />
                      <span className="pv-tendency-knob" style={{ left: `${Math.round((t.leaning ?? 0.5) * 100)}%` }} />
                    </span>
                    {t.note && <span className="pv-tendency-note">{t.note}</span>}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* 兴趣与动机 */}
          <section className="pv-section pv-grid-2">
            <div>
              <h3 className="pv-section-title pv-section-title--secondary">你为什么会选这些方向</h3>
              {profile.interest_tags.length === 0 && motivations.length === 0 ? (
                <div className="pv-hint">暂无兴趣与动机信息</div>
              ) : (
                <div className="pv-chips">
                  {profile.interest_tags.map((t: TagWithEvidence, i) => (
                    <Tag key={`i${i}`} tone="gray">{t.tag}</Tag>
                  ))}
                </div>
              )}
              {motivations.length > 0 && (
                <ul className="pv-motivations">
                  {motivations.map((m, i) => (
                    <li key={`m${i}`}>{m}</li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3 className="pv-section-title pv-section-title--secondary">价值观</h3>
              <div className="pv-hint">来自你与 AI 的访谈，将在后续版本细化呈现。</div>
            </div>
          </section>

          {/* 优势 */}
          <section className="pv-section">
            <h3 className="pv-section-title">你的优势</h3>
            {profile.strengths.length === 0 ? (
              <div className="pv-hint">暂无优势条目</div>
            ) : (
              <div className="pv-strength-grid">
                {profile.strengths.map((s, i) => (
                  <div className="pv-strength-card" key={`s${i}`}>
                    <span className="pv-strength-no">{String(i + 1).padStart(2, "0")}</span>
                    <div className="pv-strength-item">{s.item}</div>
                    {s.evidence && (
                      <details className="pv-strength-evidence">
                        <summary>AI 依据</summary>
                        <p>{s.evidence}</p>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* 成长建议（原需补齐/风险，改为建设性语气） */}
          <section className="pv-section">
            <h3 className="pv-section-title pv-section-title--secondary">还可以进一步了解</h3>
            {gapsRaw.length === 0 && profile.risks.length === 0 ? (
              <div className="pv-hint">当前画像已经比较完整，没有需要特别提示的部分。</div>
            ) : (
              <div className="pv-gaps">
                {gapsRaw.map((g, i) => (
                  <div className="pv-gap" key={`g${i}`}>
                    <div className="pv-gap-item">{g.item}</div>
                    {g.why && <div className="pv-gap-why">为什么这么判断：{g.why}</div>}
                  </div>
                ))}
                {profile.risks.map((r: Risk, i) => (
                  <div className="pv-gap" key={`r${i}`}>
                    <div className="pv-gap-item">{r.item}</div>
                    {r.strategy && <div className="pv-gap-why">建议：{r.strategy}</div>}
                  </div>
                ))}
              </div>
            )}
          </section>

          <AIResultBlock title="说明">
            <p className="pv-note">
              以上标签与判断由 AI 依据你录入的经历与访谈生成,可点击「编辑」修正;修正后的内容将以你的版本为准。AI 不会直接给出薪资、分数或匹配结论。
            </p>
          </AIResultBlock>
        </>
      )}

      {editing && (
        <div className="col" style={{ gap: 14 }}>
          <Card title="能力标签(可编辑)">
            {draft.ability_tags.map((t, i) => (
              <div className="row" key={`a${i}`} style={{ marginBottom: 8 }}>
                <Input value={t.tag} onChange={(v) => setAbility(draft, setDraft, i, "tag", v.target.value)} placeholder="标签" />
                <Input
                  placeholder="等级 1-5"
                  value={t.level ?? ""}
                  onChange={(v) => setAbility(draft, setDraft, i, "level", v.target.value)}
                />
              </div>
            ))}
          </Card>
          <Card title="风险与建议(可编辑)">
            {draft.risks.map((r, i) => (
              <div className="col" key={`r${i}`} style={{ marginBottom: 8 }}>
                <Input value={r.item} onChange={(v) => setRisk(draft, setDraft, i, "item", v.target.value)} placeholder="风险项" />
                <Input value={r.strategy} onChange={(v) => setRisk(draft, setDraft, i, "strategy", v.target.value)} placeholder="应对建议(必填)" />
              </div>
            ))}
          </Card>
          <div className="actions">
            <Button variant="ghost" onClick={() => setEditing(false)}>取消</Button>
            <Button loading={busy} icon="check" onClick={save}>
              {busy ? "保存中…" : "保存修改"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function bubbleSize(level?: number | null): "sm" | "md" | "lg" {
  if (!level) return "md";
  if (level >= 4) return "lg";
  if (level <= 2) return "sm";
  return "md";
}

function setAbility(
  draft: ProfileUpdate,
  setDraft: React.Dispatch<React.SetStateAction<ProfileUpdate>>,
  i: number,
  key: keyof AbilityTag,
  val: string
) {
  const next = draft.ability_tags.slice();
  const cur = { ...next[i]! };
  if (key === "level") cur.level = val ? Number(val) : null;
  else (cur as Record<string, unknown>)[key] = val;
  next[i] = cur;
  setDraft({ ...draft, ability_tags: next });
}

function setRisk(
  draft: ProfileUpdate,
  setDraft: React.Dispatch<React.SetStateAction<ProfileUpdate>>,
  i: number,
  key: keyof Risk,
  val: string
) {
  const next = draft.risks.slice();
  next[i] = { ...next[i]!, [key]: val };
  setDraft({ ...draft, risks: next });
}
