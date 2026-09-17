import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import BrandMark from "../../components/ui/BrandMark";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import {
  CLOSING_LINE,
  INTRO_OPENER,
  SECONDARY_HINT,
  TOTAL_TURNS,
  nextQuestion,
} from "./demoScript";

interface Msg {
  role: "ai" | "user";
  text: string;
}

/**
 * 每轮的参考回答（虚构示例，与真实用户无关）。
 *
 * 三条原则：
 *  1. 每轮 1~3 个完整句子，像真人聊天，不是问卷填空；
 *  2. 前后互相咬合——第 3 轮提到的人、「最开始…后来…」的转折，
 *     都是从第 1 轮那段经历里长出来的；
 *  3. 信息密度递减但不塌陷：越往后越偏“这个人怎么想”，
 *     因为画像本来就需要多维信息，不能只靠“你做过的项目”。
 */
const EXAMPLE_PER_TURN: Record<number, string> = {
  1:
    "我之前在一家做企业服务的公司实习过半年，主要跟着做客户反馈这块。" +
    "最开始其实就是打杂，帮忙整理表格、归档工单，什么活都接。" +
    "后来我慢慢发现，同一个问题会被不同客户反复提，就自己试着把它们归了类，" +
    "每周整理成一份问题清单给产品同学——这段大概是我第一次觉得「整理信息」这件事本身有价值。",

  2:
    "我主要负责的是把散落在客服群、工单和售后电话里的反馈收集起来，再判断哪些是真的高频问题。" +
    "一开始没有标准，我就和前端的同学聊了几次，一起定了个很粗糙的分级规则：看出现的频次、影响多少客户、有没有替代方案。" +
    "定下来之后分类快了很多，产品同学也愿意直接看我的清单开会了。",

  3:
    "最直接的结果是，那份清单里最后有三十多条被排进了版本，其中五条是反复出现的高频问题。" +
    "改完之后相关的咨询量大概少了三成，客服那边明显轻松了一点。" +
    "对我自己来说更实际的变化是：以前我提的建议没人听，后来开会的时候，产品同学会主动来问我，这个问题最近还多不多。",

  4:
    "最有成就感的应该是那种「我以为只是个小问题，结果真的影响了很多人」的时刻。" +
    "有个反馈我一开始觉得是个体的抱怨，追下去发现是某个版本的兼容问题，影响了一批客户，" +
    "后来那个问题被修掉的时候，我挺有感觉的。" +
    "消耗的部分也很明显——整理那些重复的、没有信息量的工单特别磨人，" +
    "尤其是同一句话看几十遍的时候，我会怀疑这件事到底有没有意义。",

  5:
    "我倾向于自己先把事情推到一个比较完整的程度，再拿去和别人对齐。" +
    "不是不喜欢协作，而是我发现自己如果一开始就被拉进很多会里，反而会散掉，" +
    "中间要反复同步进度也让我有点累。" +
    "但我也清楚，像刚才那种需要跨部门确认规则的事，一个人是推不动的，那种时候我还是挺依赖别人的。",

  6:
    "如果只能选一个，我选成长速度。" +
    "我现在的阶段更怕的是「这几年白过了」，而不是钱少一点。" +
    "但前提是这种成长得是我能看见的——比如我能明确说出自己这半年多会了什么，" +
    "而不是单纯地忙、单纯地加班。",

  7:
    "有。我明确不想接受那种「纯粹执行、不问为什么」的工作。" +
    "就是每天按需求做，做的过程中不能提问题，也不需要知道这个东西最后给谁用。" +
    "我在实习里也遇到过类似的阶段，那段时间我每天都挺消耗的，" +
    "最后是靠自己去追问「这个需求到底解决什么问题」才撑下来的。",

  8:
    "嗯，大方向是对的。我确实更在意做出来的东西真的起作用，也确实不喜欢纯执行。" +
    "不过有一处不太准：我不是不需要人给方向，我是需要在开始的时候有人把目标讲清楚，" +
    "中间怎么走我希望自己来。" +
    "另外稳定这件事，我不是不能接受不确定，我是不喜欢「看起来稳定、其实不可控」的那种。",
};

/** 首屏预填的示例答案（降低“你得先会说话”的门槛）。 */
const FIRST_ANSWER = EXAMPLE_PER_TURN[1] ?? "";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function DemoInterviewPage() {
  const navigate = useNavigate();
  const [started, setStarted] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [turn, setTurn] = useState(0);
  const [thinking, setThinking] = useState(false);
  const [done, setDone] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking]);

  const start = () => {
    setStarted(true);
    setMessages([{ role: "ai", text: INTRO_OPENER }]);
    setDraft(FIRST_ANSWER);
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || thinking || done) return;

    const nextTurn = turn + 1;
    setMessages((m) => [...m, { role: "user", text }]);
    setDraft("");
    setTurn(nextTurn);
    setThinking(true);

    // 拟人停顿：让“AI 正在读你刚才说的话”这件事被看见
    await sleep(700);

    if (nextTurn >= TOTAL_TURNS) {
      setMessages((m) => [...m, { role: "ai", text: CLOSING_LINE }]);
      setDone(true);
    } else {
      setMessages((m) => [...m, { role: "ai", text: nextQuestion(nextTurn, text) }]);
    }
    setThinking(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const exampleForThisTurn = EXAMPLE_PER_TURN[turn + 1];

  return (
    <div className="dmo">
      <header className="dmo-topbar">
        <div className="dmo-topbar__brand">
          <BrandMark size={24} />
          <span>职己职彼</span>
          {/* 身份标识：低饱和，不作免责声明口吻 */}
          <span className="dmo-topbar__tag">在线 Demo · 固定数据演示</span>
        </div>
        <button className="dmo-skip" onClick={() => navigate("/profile")}>
          跳过，直接看 Demo 画像
        </button>
      </header>

      <main className="dmo-main">
        {!started ? (
          /* 首屏：大面积留白 + 一句引导 + 单一主 CTA（辅助入口低权重） */
          <section className="dmo-intro">
            <div className="dmo-intro__avatar" aria-hidden>
              <Icon name="sparkle" size={26} />
            </div>
            <h1 className="dmo-intro__title">先花几分钟，让 AI 认识你</h1>
            <p className="dmo-intro__body">
              AI 会像真实访谈那样，接着你的话一轮一轮问下去，最后给你一份能追溯来源的职业画像。
            </p>

            <div className="dmo-intro__cta">
              <Button variant="primary" size="lg" icon="sparkle" onClick={start}>
                从认识自己开始 →
              </Button>
            </div>

            <p className="dmo-intro__alt">{SECONDARY_HINT}</p>

            <p className="dmo-intro__note">
              当前使用固定示例数据展示完整流程，聊天内容只在你的浏览器里。
              想体验真实 AI 对话？注册后即可开始。
            </p>
          </section>
        ) : (
          /* 多轮访谈 */
          <>
            <div className="dmo-progress" aria-hidden>
              <div className="dmo-progress__bar" style={{ width: `${(turn / TOTAL_TURNS) * 100}%` }} />
            </div>

            <div className="dmo-scroll" ref={scrollRef}>
              {messages.map((m, i) => (
                <div key={i} className={`dmo-msg dmo-msg--${m.role}`}>
                  {m.role === "ai" && (
                    <span className="dmo-msg__avatar" aria-hidden>
                      <Icon name="sparkle" size={14} />
                    </span>
                  )}
                  <div className="dmo-bubble">{m.text}</div>
                </div>
              ))}
              {thinking && (
                <div className="dmo-msg dmo-msg--ai">
                  <span className="dmo-msg__avatar" aria-hidden>
                    <Icon name="sparkle" size={14} />
                  </span>
                  <div className="dmo-bubble dmo-bubble--thinking">正在读你刚才说的话…</div>
                </div>
              )}
            </div>

            <div className="dmo-composer">
              {done ? (
                <div className="dmo-done">
                  <Button variant="primary" icon="profile" onClick={() => navigate("/profile")}>
                    查看 AI 给我的职业画像
                  </Button>
                  <span className="dmo-done__hint">
                    接下来看到的是 Demo 数据，完整展示画像 → 探索 → 岗位 → 准备 → 追踪 → Offer
                  </span>
                </div>
              ) : (
                <>
                  <div className="dmo-composer__box">
                    <textarea
                      className="dmo-textarea"
                      rows={3}
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={onKeyDown}
                      placeholder="说说你的经历、你在意什么…（Enter 发送，Shift+Enter 换行）"
                      aria-label="你的回答"
                    />
                    <Button
                      variant="primary"
                      size="sm"
                      loading={thinking}
                      disabled={!draft.trim()}
                      onClick={() => void send()}
                    >
                      发送
                    </Button>
                  </div>
                  {exampleForThisTurn && !draft && (
                    <button className="dmo-example" onClick={() => setDraft(exampleForThisTurn)}>
                      <Icon name="bulb" size={13} /> 不知道说什么？点这里用一段示例回答
                    </button>
                  )}
                  <span className="dmo-composer__count">
                    第 {Math.min(turn + 1, TOTAL_TURNS)} / {TOTAL_TURNS} 轮
                  </span>
                </>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
