import type { OnboardingSession } from "../../api/client";
import Icon from "../../components/ui/Icon";

interface Props {
  session: OnboardingSession | null;
  onCorrectTag: (tag: string) => void;
  /** compact: 用于桌面端窄浮层，隐藏标题、收紧间距 */
  compact?: boolean;
}

// 渐进式理解展示:标签 + 短句 + 开放问题。绝不设计成数据库字段表。
export default function UnderstandingPanel({ session, onCorrectTag, compact }: Props) {
  const understanding = session?.understanding;
  const tags = understanding?.tags ?? [];
  const sentences = understanding?.sentences ?? [];
  const wants = session?.wants_to_know ?? [];

  return (
    <div className={compact ? "onb-understand onb-understand--compact" : "onb-understand"}>
      {!compact && (
        <div className="onb-understand-head">
          <Icon name="eye" size={16} />
          <span>我目前对你的了解</span>
        </div>
      )}

      {tags.length === 0 && sentences.length === 0 ? (
        <div className="onb-understand-empty">聊几句之后,这里会慢慢出现我对你的理解。</div>
      ) : (
        <>
          <div className="onb-understand-tags">
            {tags.map((t, i) => (
              <button key={i} className="onb-understand-tag" onClick={() => onCorrectTag(t)} title="点击可纠正">
                <Icon name="check" size={12} />
                {t}
                <Icon name="edit" size={11} className="onb-understand-tag-edit" />
              </button>
            ))}
          </div>

          {sentences.length > 0 && (
            <ul className="onb-understand-sentences">
              {sentences.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          )}
        </>
      )}

      {wants.length > 0 && (
        <div className="onb-understand-wants">
          <div className="onb-understand-wants-title">我还想了解</div>
          <ul>
            {wants.map((w, i) => (
              <li key={i}>
                <Icon name="bulb" size={12} />
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
