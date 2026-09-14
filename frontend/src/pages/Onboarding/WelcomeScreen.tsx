import Icon from "../../components/ui/Icon";
import { AuroraBackdrop } from "../../components/ui/Illustrations";

interface Props {
  onStart: () => void;
}

// 登录后首屏：先讲清产品定位，再给一个主 CTA。
// V3：极光 SVG 背景 + 渐变英雄按钮 + 渐变标语——"产品气质"在这里定调。
export default function WelcomeScreen({ onStart }: Props) {
  return (
    <div className="onb-welcome">
      <AuroraBackdrop />
      <div className="onb-welcome-inner">
        <div className="onb-ai-avatar" aria-hidden>
          <Icon name="sparkles" size={20} />
        </div>

        <h1 className="onb-welcome-title">职己职彼</h1>
        <p className="onb-welcome-lead grad-text">懂职场，也更懂自己。</p>

        <p className="onb-welcome-body">
          普通大模型能回答你一次求职问题，却记不住你一路走来做过什么、在意什么。
          职己职彼先把你的经历、能力和偏好，沉淀成一份会随你成长、可反复使用的职业画像，
          再陪你探索方向、判断岗位、追踪投递、比较 Offer。
        </p>

        <p className="onb-welcome-note">
          AI 帮你整理信息、看清关系、给出视角——但去哪家、怎么选，始终是你自己的决定。
        </p>

        <button className="btn btn--hero btn--lg onb-start" onClick={onStart}>
          从认识自己开始
          <Icon name="arrowRight" size={18} />
        </button>

        <div className="onb-welcome-hint">
          也可以稍后上传简历，或直接从零聊起，怎么舒服怎么来。
        </div>
      </div>
    </div>
  );
}
