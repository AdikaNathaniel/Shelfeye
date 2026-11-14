"use client";

import { useEffect, useRef, useState } from "react";
import { type ChatMessage, UnauthorizedError, sendChat } from "@/lib/api";
import { useShelfEye } from "@/components/DataProvider";
import { ChatIcon } from "@/components/Icons";

const SUGGESTIONS = [
  "What's running low or out of stock?",
  "How many units are on the shelves in total?",
  "What was taken today?",
  "Which products moved the most this week?",
];

export default function ChatPage() {
  const { user, signOut } = useShelfEye();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || sending) return;
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setDraft("");
    setError(null);
    setSending(true);
    try {
      const reply = await sendChat(next);
      setMessages([...next, { role: "assistant", content: reply }]);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        signOut();
        return;
      }
      setMessages(next); // keep the question; let them retry
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(draft);
    }
  }

  const empty = messages.length === 0;

  return (
    <div className="chat-wrap">
      <div className="chat-scroll" ref={scrollRef}>
        {empty ? (
          <div className="chat-empty">
            <div className="chat-empty-icon"><ChatIcon size={26} /></div>
            <h2>Ask about your stock</h2>
            <p className="muted">
              I can see your live inventory and recent activity. Ask me anything about the products on your shelves.
            </p>
            <div className="chat-suggests">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chat-suggest" onClick={() => ask(s)} disabled={sending}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-thread">
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg ${m.role}`}>
                <div className="chat-bubble">{m.content}</div>
              </div>
            ))}
            {sending && (
              <div className="chat-msg assistant">
                <div className="chat-bubble chat-typing"><span /><span /><span /></div>
              </div>
            )}
          </div>
        )}
      </div>

      {error && <div className="chat-error" role="alert">{error}</div>}

      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
        }}
      >
        <textarea
          ref={inputRef}
          className="chat-input"
          placeholder={`Ask about your stock, ${user.name.split(/\s+/)[0]}…`}
          value={draft}
          rows={1}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={sending}
        />
        <button type="submit" className="btn btn-primary chat-send" disabled={sending || !draft.trim()}>
          Send
        </button>
      </form>
      <p className="chat-note muted small">
        Answers come from your live shelf data. Double-check anything critical.
      </p>
    </div>
  );
}
