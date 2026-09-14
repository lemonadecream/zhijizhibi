import type { OnboardingSession } from "../../api/client";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";

interface Props {
  session: OnboardingSession | null;
  onFinalize: () => void;
  onBack: () => void;
}

// 访谈完成确认：以 AI 口吻给出候选摘要，融入对话流（不再独立大卡片居中）。
export default function CompletionConfirm({ session, onFinalize, onBack }: Props) {
  const summary = session?.summary_pending?.summary || "我已经大致了解你了，可以开始生成你的职业画像。";
  const tags = session?.understanding?.tags ?? [];

  return (
    <div className="onb-complete">
      <div className="onb-msg onb-msg--ai">
        <span className="onb-msg-avatar" aria-hidden>
          <Icon name="sparkles" size={14} />
        </span>
        <div className="onb-bubble onb-complete-bubble">
          <p className="onb-complete-lead">我大概了解你了。如果让我现在总结一下：</p>
          <p className="onb-complete-summary">{summary}</p>

          {tags.length > 0 && (
            <div className="onb-complete-tags">
              {tags.map((t, i) => (
                <span key={i} className="tag tag--blue">
                  {t}
                </span>
              ))}
            </div>
          )}

          <div className="onb-complete-actions">
            <Button variant="ghost" size="sm" onClick={onBack} icon="edit">
              我还想补充一些
            </Button>
            <Button onClick={onFinalize} icon="sparkles" size="md">
              生成我的职业画像
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
