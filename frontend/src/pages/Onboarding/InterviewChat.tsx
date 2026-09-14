import { useEffect, useRef, useState } from "react";
import type { OnboardingSession, OnboardingStepResult } from "../../api/client";
import UnderstandingPanel from "./UnderstandingPanel";
import ResumeInline, { type ResumeEntryMode } from "./ResumeInline";
import ExperienceTemplateDrawer from "./ExperienceTemplateDrawer";
import BrandMark from "../../components/ui/BrandMark";
import Drawer from "../../components/ui/Drawer";
import Modal from "../../components/ui/Modal";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";

interface Props {
  session: OnboardingSession | null;
  onStep: (message: string) => Promise<OnboardingStepResult>;
  /** 流式版本（可选）：delta 增量渲染 AI 回复；失败时由调用方回退 onStep */
  onStepStream?: (
    message: string,
    h: { onDelta(t: string): void; onDone(res: OnboardingStepResult): void; onError(m: string): void }
  ) => void;
  onCorrect: (dimension: string, from_text: string, to_text: string) => Promise<void>;
  onComplete: () => void;
  onExit: () => void;
  /** 打开入口浮层（上传/粘贴/从零） */
  onOpenEntry: (mode: ResumeEntryMode) => void;
  /** 录入完成后注入会话 */
  entryMode: ResumeEntryMode | null;
  onEntryConfirmed: (resumeId: number | null) => void;
  onEntryCancel: () => void;
}

type Msg = { role: "user" | "ai"; text: string };

export default function InterviewChat({
  session,
  onStep,
  onStepStream,
  onCorrect,
  onComplete,
  onExit,
  onOpenEntry,
  entryMode,
  onEntryConfirmed,
  onEntryCancel,
}: Props) {
  const [messages, setMessages] = useState<Msg[]>(
    session?.history?.filter((h) => h.role === "user" || h.role === "ai").map((h) => ({ role: h.role as "user" | "ai", text: h.text })) ?? []
  );
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamText, setStreamText] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tplOpen, setTplOpen] = useState(false);
  const [correcting, setCorrecting] = useState<{ tag: string; value: string } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, streamText, entryMode]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);

    const finishWith = (res: OnboardingStepResult) => {
      setMessages((m) => [...m, { role: "ai", text: res.ai_response }]);
      if (res.completion_ready) {
        window.setTimeout(onComplete, 500);
      }
    };

    if (onStepStream) {
      // 流式路径：AI 回复增量渲染；异常时回退非流式
      setStreamText("");
      onStepStream(text, {
        onDelta: (t) => setStreamText((prev) => (prev ?? "") + t),
        onDone: (res) => {
          setStreamText(null);
          setBusy(false);
          finishWith(res);
        },
        onError: () => {
          setStreamText(null);
          onStep(text)
            .then((res) => {
              setBusy(false);
              finishWith(res);
            })
            .catch(() => {
              setBusy(false);
              setMessages((m) => [...m, { role: "ai", text: "抱歉，我这边出了点小问题，能再发一次吗？" }]);
            });
        },
      });
      return;
    }

    setBusy(true);
    try {
      const res = await onStep(text);
      finishWith(res);
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "抱歉，我这边出了点小问题，能再发一次吗？" }]);
    } finally {
      setBusy(false);
    }
  };

  const handleCorrectTag = (tag: string) => {
    setCorrecting({ tag, value: "" });
  };

  const submitCorrect = async () => {
    if (!correcting) return;
    const { tag, value } = correcting;
    setCorrecting(null);
    await onCorrect("D2", tag, value.trim());
  };

  // 已确认的理解标签数量，用于轻量浮层标题
  const understandCount = (session?.understanding?.tags?.length ?? 0) + (session?.understanding?.sentences?.length ?? 0);

  // 六维度覆盖度（D1-D6）：顶部细进度条的数据源
  const dimState = session?.dimension_state ?? [];
  const dimCovered = dimState.filter((d) => d.covered).length;
  const dimTotal = dimState.length > 0 ? dimState.length : 0;

  return (
    <div className="onb-chat">
      {/* 极简品牌条 */}
      <header className="onb-topbar">
        <div className="onb-topbar-brand">
          <BrandMark size={28} />
          职己职彼
        </div>
        <button className="onb-topbar-exit" onClick={onExit}>
          稍后再说
        </button>
      </header>

      {/* 对话主体（绝对视觉中心） */}
      <main className="onb-chat-main">
        {/* 六维度覆盖度：细进度条，让"还差多少完成"始终可见 */}
        {dimTotal > 0 && (
          <div
            className="onb-dim-progress"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={dimTotal}
            aria-valuenow={dimCovered}
            aria-label={`访谈维度覆盖进度 ${dimCovered}/${dimTotal}`}
          >
            <div className="onb-dim-progress__bar" style={{ width: `${Math.round((dimCovered / dimTotal) * 100)}%` }} />
          </div>
        )}
        <div className="onb-chat-scroll" ref={scrollRef}>
          {entryMode && (
            <ResumeInline mode={entryMode} onConfirmed={onEntryConfirmed} onCancel={onEntryCancel} />
          )}

          {messages.length === 0 && !entryMode && (
            <div className="onb-chat-empty">
              在下面告诉我你的经历、兴趣或现在的迷茫，怎么开头都行。
              <br />
              也可以先用上面的入口上传简历或填个模板。
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`onb-msg onb-msg--${m.role}`}>
              {m.role === "ai" && (
                <span className="onb-msg-avatar" aria-hidden>
                  <Icon name="sparkles" size={14} />
                </span>
              )}
              <div className="onb-bubble">{m.text}</div>
            </div>
          ))}

          {streamText !== null && (
            <div className="onb-msg onb-msg--ai">
              <span className="onb-msg-avatar" aria-hidden>
                <Icon name="sparkles" size={14} />
              </span>
              <div className="onb-bubble onb-bubble--streaming">
                {streamText}
                <span className="stream-caret" aria-hidden />
              </div>
            </div>
          )}

          {busy && streamText === null && (
            <div className="onb-msg onb-msg--ai">
              <span className="onb-msg-avatar" aria-hidden>
                <Icon name="sparkles" size={14} />
              </span>
              {/* 思考胶囊：比起三个点，用文字让"AI 在做什么"可感知 */}
              <div className="onb-bubble onb-thinking">
                <span className="onb-bubble--typing" aria-hidden>
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                </span>
                <span className="onb-thinking-text">AI 正在理解你的经历…</span>
              </div>
            </div>
          )}
        </div>

        {/* 底部固定输入条 + 辅助入口 */}
        <footer className="onb-composer">
          <div className="onb-composer-entries">
            <button className="onb-entry-chip" onClick={() => onOpenEntry("upload")}>
              <Icon name="upload" size={15} />
              上传简历
            </button>
            <button className="onb-entry-chip" onClick={() => setTplOpen(true)}>
              <Icon name="doc" size={15} />
              填写经历模板
            </button>
          </div>
          <div className="onb-composer-box">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder="用你自己的话回答就行…（Enter 发送，Shift+Enter 换行）"
              rows={2}
            />
            <button className="onb-send" onClick={send} disabled={!input.trim() || busy} aria-label="发送">
              <Icon name="arrowRight" size={18} />
            </button>
          </div>
        </footer>
      </main>

      {/* 桌面端轻量理解浮层（窄列，非大侧栏） */}
      <aside className="onb-aside">
        <button className="onb-aside-toggle" onClick={() => setDrawerOpen(true)}>
          <Icon name="eye" size={15} />
          AI 正在认识你
          {understandCount > 0 && <span className="onb-aside-count">{understandCount}</span>}
        </button>
        <UnderstandingPanel session={session} onCorrectTag={handleCorrectTag} compact />
      </aside>

      {/* 移动端理解 Drawer */}
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="AI 正在认识你">
        <UnderstandingPanel session={session} onCorrectTag={handleCorrectTag} />
      </Drawer>

      {/* 经历模板 Drawer */}
      <ExperienceTemplateDrawer open={tplOpen} onClose={() => setTplOpen(false)} />

      {/* 纠正理解：产品内一致交互，替代原生 window.prompt */}
      <Modal
        open={!!correcting}
        onClose={() => setCorrecting(null)}
        title={correcting ? `纠正理解「${correcting.tag}」` : ""}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCorrecting(null)}>取消</Button>
            <Button variant="primary" onClick={submitCorrect}>保存</Button>
          </>
        }
      >
        <Input
          label="修改为（留空表示删除这条理解）"
          value={correcting?.value ?? ""}
          onChange={(e) => setCorrecting((c) => (c ? { ...c, value: e.target.value } : c))}
          placeholder="输入新的内容…"
          autoFocus
        />
      </Modal>
    </div>
  );
}
