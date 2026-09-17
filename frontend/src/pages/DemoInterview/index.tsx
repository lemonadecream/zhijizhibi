import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import BrandMark from "../../components/ui/BrandMark";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { CLOSING_LINE, DEMO_GUIDES, TOTAL_TURNS, nextQuestion, type DemoGuide } from "./demoScript";

interface Msg {
  role: "ai" | "user";
  text: string;
}

/** 每轮追问的参考回答——访客不想打字时一键填入，Demo 不该卡在"你得先会说话"。 */
const EXAMPLE_PER_TURN: Record<number, string> = {
  1: "我主要负责把客户反馈归类和分级，再整理成产品同学能直接用的需求清单。",
  2: "最后这份清单有 30 多条被排进了版本，其中 5 条是高频问题，处理完之后相关咨询少了大概三成。",
  3: "我最看重的是能不能看到自己做的事真的起作用，其次是团队里有人愿意带我。",
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function DemoInterviewPage() {
  const navigate = useNavigate();
  const [guide, setGuide] = useState<DemoGuide | null>(null);
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

  const pickGuide = (g: DemoGuide) => {
    setGuide(g);
    setMessages([{ role: "ai", text: g.opener }]);
    setDraft(g.example);
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || thinking || done) return;

    const nextTurn = turn + 1;
    setMessages((m) => [...m, { role: "user", text }]);
    setDraft("");
    setTurn(nextTurn);
    setThinking(true);

    // 拟人停顿：让"AI 正在读你刚才说的话"这件事被看见
    await sleep(650);

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

  const exampleForThisTurn = EXAMPLE_PER_TURN[turn];

  return (
    <div className="dmo">
      <header className="dmo-topbar">
        <div className="dmo-topbar__brand">
          <BrandMark size={24} />
          <span>职己职彼</span>
          <span className="dmo-topbar__tag">在线 Demo</span>
        </div>
        <button className="dmo-skip" onClick={() => navigate("/profile")}>
          跳过，直接看 Demo 画像
        </button>
      </header>

      <main className="dmo-main">
        {!guide ? (
          /* 第一步：冷启动引导 —— 不要求上传简历，也不要求"会说话" */
          <section className="dmo-intro">
            <div className="dmo-intro__avatar" aria-hidden>
              <Icon name="sparkle" size={26} />
            </div>
            <h1 className="dmo-intro__title">先花 1 分钟，让 AI 认识你</h1>
            <p className="dmo-intro__body">
              这是在线 Demo，<strong>不需要注册、不需要上传简历</strong>。
              聊几句就够——AI 会像真实访谈那样接着你的话追问，最后给你一份可追溯的职业画像。
            </p>

            <div className="dmo-guides">
              {DEMO_GUIDES.map((g, i) => (
                <button
                  key={g.label}
                  type="button"
                  className="dmo-guide"
                  onClick={() => pickGuide(g)}
                >
                  <Icon name={i === 3 ? "bulb" : "doc"} size={16} />
                  <span>{g.label}</span>
                </button>
              ))}
            </div>

            <p className="dmo-intro__note">
              聊天内容只在你的浏览器里，不会写入 Demo 账号的画像数据。
            </p>
          </section>
        ) : (
          /* 第二步：多轮访谈 */
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
                      rows={2}
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={onKeyDown}
                      placeholder="说说你的经历、你在意什么…（Enter 发送）"
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
                      <Icon name="bulb" size={13} /> 不知道说什么？点这里用一句示例
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
