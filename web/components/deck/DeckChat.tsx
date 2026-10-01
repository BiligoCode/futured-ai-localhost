"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { useI18n } from "@/lib/i18n";
import type { ChatMessage, EditLog } from "@/lib/types";

export type ActiveSlide = { id: string; label: string };

/** The assistant beside the slides: answers, edits, or both. The workspace owns the request and the merge. */
export function DeckChat({ messages, activeSlide, selection, busy, canUndo, onSend, onUndo, onClearSelection, onClearSlide, onJump, slideLabel }: {
  messages: ChatMessage[];
  activeSlide: ActiveSlide | null;
  selection: string | null;
  busy: boolean;
  canUndo: boolean;
  onSend: (message: string, useSlide: boolean, useSelection: boolean, signal: AbortSignal) => Promise<void>;
  onUndo: () => void;
  onClearSelection: () => void;
  onClearSlide: () => void;
  onJump: (slideId: string) => void;
  slideLabel: (slideId: string) => string;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [useSlide, setUseSlide] = useState(true);
  const [useSelection, setUseSelection] = useState(true);
  const controller = useRef<AbortController | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [messages.length, busy]);

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setError(null);
    const ac = new AbortController();
    controller.current = ac;
    try {
      await onSend(message, useSlide && !!activeSlide, useSelection && !!selection, ac.signal);
      setText("");
    } catch (err) {
      if (ac.signal.aborted) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      controller.current = null;
    }
  }

  const lastAssistantWithEdits = [...messages].reverse().find((m) => m.role === "assistant" && m.edits.length > 0);

  function chipLabel(e: EditLog) {
    const name = e.title || slideLabel(e.slide_id);
    return t.chip[e.op](name);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-rule px-5 py-3">
        <h2 className="font-serif text-xl font-semibold">{t.askLara}</h2>
      </div>

      <div ref={list} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4" aria-live="polite">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-muted">{t.chatIntro}</p>
            <ul className="space-y-2">
              {t.chatSuggestions.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => {
                      setText(s);
                      textarea.current?.focus();
                    }}
                    className="w-full rounded-lg border border-rule bg-paper px-3 py-2 text-left text-sm hover:border-accent hover:text-accent"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <p className="max-w-[85%] rounded-2xl rounded-br-md bg-sunken px-4 py-2 text-sm whitespace-pre-wrap">{m.content}</p>
            </div>
          ) : (
            <div key={i} className="space-y-2">
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{m.content}</p>
              {m.edits.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  {m.edits.map((e, j) => (
                    <button
                      key={j}
                      type="button"
                      onClick={() => onJump(e.slide_id)}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        e.op === "delete" ? "bg-rec-soft text-danger-ink" : "bg-accent-soft text-accent hover:bg-accent hover:text-white"
                      }`}
                    >
                      {chipLabel(e)}
                    </button>
                  ))}
                  {m === lastAssistantWithEdits && canUndo && (
                    <button type="button" onClick={onUndo} className="ml-1 text-xs font-semibold text-muted underline underline-offset-2 hover:text-ink">
                      {t.undoAi}
                    </button>
                  )}
                </div>
              )}
            </div>
          ),
        )}
        {busy && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <span className="pulse-soft h-2 w-2 rounded-full bg-gold" aria-hidden="true" />
            {t.thinking}
            <button type="button" onClick={() => controller.current?.abort()} className="font-semibold text-ink underline underline-offset-2">
              {t.stop}
            </button>
          </p>
        )}
        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}
      </div>

      <form onSubmit={submit} className="border-t border-rule p-3">
        <div className="rounded-xl border border-rule-strong bg-surface transition-[border-color,box-shadow] focus-within:border-accent focus-within:shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-accent)_22%,transparent)]">
          <div className="flex flex-wrap gap-1.5 px-3 pt-2 empty:hidden">
            {activeSlide && useSlide && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft py-0.5 pr-0.5 pl-2.5 text-xs font-semibold text-accent">
                <Icon name="slides" size={13} />
                {activeSlide.label}
                <button type="button" onClick={() => { setUseSlide(false); onClearSlide(); }} className="grid h-5 w-5 place-items-center rounded-full hover:bg-accent hover:text-white" aria-label={t.dontUseSlide}>
                  <Icon name="close" size={11} />
                </button>
              </span>
            )}
            {selection && useSelection && (
              <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-gold-soft py-0.5 pr-0.5 pl-2.5 text-xs font-semibold text-gold-ink">
                <span className="truncate">{t.useSelection}: “{selection.length > 40 ? selection.slice(0, 40) + "…" : selection}”</span>
                <button type="button" onClick={() => { setUseSelection(false); onClearSelection(); }} className="grid h-5 w-5 shrink-0 place-items-center rounded-full hover:bg-gold hover:text-white" aria-label={t.dontUseSelection}>
                  <Icon name="close" size={11} />
                </button>
              </span>
            )}
          </div>
          <textarea
            ref={textarea}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onFocus={() => {
              setUseSlide(true);
              setUseSelection(true);
            }}
            rows={3}
            disabled={busy}
            aria-label={t.askLara}
            placeholder={t.chatPlaceholder}
            className="block w-full resize-none bg-transparent px-3 py-2 text-sm leading-relaxed placeholder:text-faint focus-visible:outline-none disabled:opacity-60"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit();
            }}
          />
          <div className="flex items-center gap-2 px-2 pb-2">
            <span className="flex-1 text-xs text-faint">{t.ctrlEnter}</span>
            <button type="submit" disabled={busy || !text.trim()} className="btn btn-primary py-1.5">
              <Icon name="send" size={16} />
              {t.send}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
