/**
 * 在线 Demo 的「AI 认识你」冷启动脚本。
 *
 * 为什么放在前端而不是调后端 interview_step：
 *  - Demo 账号是**多人共用**的，而 career_interview_session.user_id 是 UNIQUE。
 *    走后端会让访客 A 的答题状态影响访客 B（甚至把先来的会话推到 completed，
 *    后来的直接撞「访谈已完成」报错），且 append_turn 会持续污染同一份会话。
 *  - 本模块是**纯确定性函数**：不联网、不调用任何 LLM、零费用、可单测。
 *
 * 追问不是静态欢迎语：每一步都会从用户真实输入里抽取可引用的片段（公司/项目/数字/偏好），
 * 再据此组织追问，形成"有上下文关系"的多轮对话。
 */

export interface DemoGuide {
  /** 冷启动引导项文案 */
  label: string;
  /** 选它之后 AI 的第一句 */
  opener: string;
  /** 预填进输入框的示例回答（可直接发送，也可以改） */
  example: string;
}

/** 四轮交互后收束——对应「3~4 轮自然语言交互」。 */
export const TOTAL_TURNS = 4;

export const DEMO_GUIDES: DemoGuide[] = [
  {
    label: "从实习经历开始",
    opener:
      "好，我们从实习聊起。说一段你印象最深的实习吧——在哪儿、大概做什么，以及你负责的那部分。",
    example: "我在一家做企业服务的公司实习过半年，主要负责客户反馈的收集和整理，每周输出一份问题清单给产品同学。",
  },
  {
    label: "从项目经历开始",
    opener:
      "那就聊项目。挑一个你自己参与度最高的，讲讲它的目标和你实际做了什么。",
    example: "我做过一个校园二手交易的小程序，我负责需求调研和前期原型，上线后有 800 多个同学用过。",
  },
  {
    label: "说说你喜欢什么样的工作",
    opener:
      "换个角度也行。先说说你不想要什么，再说说你希望的工作是什么样子。",
    example: "我不太想做纯执行、每天重复的活儿；希望工作里能有自己判断的空间，也能看到结果。",
  },
  {
    label: "不知道说什么，让 AI 带着你聊",
    opener:
      "没关系，我问你答就行。第一个问题很简单：最近一年里，你花时间最多的一件事是什么？",
    example: "最近一年花时间最多的是在准备秋招，同时还在做一个校级项目的数据整理工作。",
  },
];

/** 从自由文本里抽取一个可引用的"主体"（公司 / 项目 / 引号内容）。 */
export function pickSubject(text: string): string | null {
  const t = (text || "").trim();
  if (!t) return null;

  // 「XX」/ “XX” / "XX" —— 用户自己强调过的名词最值得引用
  const quoted = t.match(/[「“"]([^」”"]{2,16})[」”"]/);
  if (quoted) return quoted[1] ?? null;

  // 「在 XX 公司/团队/项目…」
  const org = t.match(
    /在([\u4e00-\u9fa5A-Za-z0-9]{2,12}?)(?:公司|集团|科技|工作室|团队|部门|项目|实习)/
  );
  if (org) return org[1] ?? null;

  // 「XX 公司/项目」出现在句首
  const head = t.match(/^([\u4e00-\u9fa5A-Za-z0-9]{2,12}?)(?:公司|集团|工作室|项目)/);
  if (head) return head[1] ?? null;

  return null;
}

const HAS_NUMBER = /\d|百分|提升|增长|降低|下降|收益|指标|转化|留存/;
const HAS_PREFERENCE = /看重|希望|喜欢|不想|不愿意|避免|介意|重要|优先/;

/**
 * 根据"已完成轮次 + 历史输入"生成下一句 AI 追问。
 *
 * @param turn  已经发生的用户发言条数（第 1 次发送后 turn = 1）
 * @param last  用户最近一条发言
 * @param answerForGuide 该轮是否已经用过引导语（避免首轮重复 opener）
 */
export function nextQuestion(turn: number, last: string): string {
  const subject = pickSubject(last);

  switch (turn) {
    case 1:
      return subject
        ? `「${subject}」这段听起来有内容。你在里面具体负责的是哪一部分？`
        : "听起来你有一些具体经历。挑其中最有代表性的一段——你当时具体做了什么？";

    case 2:
      return HAS_NUMBER.test(last)
        ? "你提到了结果，这个能再具体一点吗？比如一个可以被衡量的变化。"
        : "这件事最后带来了什么变化？有没有一个能被衡量的结果，哪怕是体验上的改善？";

    case 3:
      return HAS_PREFERENCE.test(last)
        ? "你的偏好我记下来了。如果只能说一条「绝对不妥协」的，会是哪一条？"
        : "那在做选择的时候，你最看重什么？薪水、成长空间、稳定性，还是别的？";

    default:
      return "";
  }
}

/** 最后一轮的收束语（第 TOTAL_TURNS 次发送之后）。 */
export const CLOSING_LINE =
  "差不多了。我已经能勾勒出你的画像轮廓：你怎么做事、在意什么、适合什么环境。要不要看看 AI 给你的定位？";
