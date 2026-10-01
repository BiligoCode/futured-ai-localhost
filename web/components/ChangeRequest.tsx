"use client";

import { useState } from "react";

import { reviseVideo } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { clock } from "@/lib/time";
import type { CutKind, EditSummary, Project } from "@/lib/types";

import { Icon } from "./Icon";

export function ChangeRequest({ project, cut, playerAt, onClearPlayerAt, onChange }: {
  project: Project;
  cut: CutKind;
  /** The paused player's position, offered as context for the request. */
  playerAt: number | null;
  onClearPlayerAt: () => void;
  onChange: (p: Project) => void;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [planned, setPlanned] = useState<EditSummary[] | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setSending(true);
    setError(null);
    try {
      const result = await reviseVideo(project.id, text.trim(), cut, playerAt);
      setPlanned(result.edits);
      setText("");
      onClearPlayerAt();
      onChange(result.project);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="panel space-y-4 p-5 sm:p-6" aria-labelledby="change-heading">
      <div>
        <h2 id="change-heading" className="font-serif text-2xl font-semibold">
          {t.askChange}
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">{t.askChangeIntro}</p>
      </div>
      <form onSubmit={submit} className="rounded-xl border border-rule-strong bg-surface transition-[border-color,box-shadow] focus-within:border-accent focus-within:shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-accent)_22%,transparent)]">
        <textarea
          name="change"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          disabled={sending}
          autoComplete="off"
          aria-label={t.describeChange}
          placeholder={t.changePlaceholder}
          className="block w-full resize-y rounded-t-xl bg-transparent px-4 pt-3 pb-2 font-serif text-lg leading-relaxed placeholder:text-faint focus-visible:outline-none disabled:opacity-60"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
          }}
        />
        <div className="flex flex-wrap items-center gap-2 px-3 pb-3">
          {playerAt !== null && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft py-1 pr-1 pl-2.5 text-xs font-semibold text-accent tabular-nums">
              <Icon name="pin" size={14} />
              {t.atTime(clock(playerAt))}
              <button
                type="button"
                onClick={onClearPlayerAt}
                className="grid h-5 w-5 place-items-center rounded-full hover:bg-accent hover:text-white"
                aria-label={t.dontUsePosition}
              >
                <Icon name="close" size={12} />
              </button>
            </span>
          )}
          <span className="hidden flex-1 text-right text-xs text-faint sm:block">{t.ctrlEnter}</span>
          <button type="submit" disabled={sending || !text.trim()} className="btn btn-primary ml-auto sm:ml-0">
            {sending ? t.finding : t.makeChange}
          </button>
        </div>
      </form>
      <div aria-live="polite" className="space-y-2">
        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}
        {planned && (
          <ul className="divide-y divide-rule rounded-lg bg-paper text-sm">
            {planned.map((e) => (
              <li key={e.scene_id} className="flex gap-3 px-3 py-2">
                <span className="shrink-0 font-semibold text-gold-ink tabular-nums">
                  {e.start !== null && e.end !== null ? `${clock(e.start)}–${clock(e.end)}` : "—"}
                </span>
                <span className="min-w-0 break-words">
                  {e.summary}
                  <span className="ml-2 text-xs text-muted">
                    {[e.animation && t.kindAnimation, e.narration && t.kindNarration].filter(Boolean).join(" & ")}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
