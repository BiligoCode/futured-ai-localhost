"use client";

import { useState } from "react";

import { reviseVideo } from "@/lib/api";
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
          Ask for a change
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Describe it the way you would to a colleague: what happens on screen, what is said, or a time in the video. Lara finds the right moment and changes only that.
        </p>
      </div>
      <form onSubmit={submit} className="rounded-xl border border-rule-strong bg-surface transition-[border-color,box-shadow] focus-within:border-accent focus-within:shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-accent)_22%,transparent)]">
        <textarea
          name="change"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          disabled={sending}
          autoComplete="off"
          aria-label="Describe a change to the video"
          placeholder={"e.g. “When the array gets iterated, move the pointer more slowly”\nor “At 0:32 explain why we split the array in half”"}
          className="block w-full resize-y rounded-t-xl bg-transparent px-4 pt-3 pb-2 font-serif text-lg leading-relaxed placeholder:text-faint focus-visible:outline-none disabled:opacity-60"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
          }}
        />
        <div className="flex flex-wrap items-center gap-2 px-3 pb-3">
          {playerAt !== null && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft py-1 pr-1 pl-2.5 text-xs font-semibold text-accent tabular-nums">
              <Icon name="pin" size={14} />
              At {clock(playerAt)} in the video
              <button
                type="button"
                onClick={onClearPlayerAt}
                className="grid h-5 w-5 place-items-center rounded-full hover:bg-accent hover:text-white"
                aria-label="Don’t use the player position"
              >
                <Icon name="close" size={12} />
              </button>
            </span>
          )}
          <span className="hidden flex-1 text-right text-xs text-faint sm:block">Ctrl&nbsp;+&nbsp;Enter to send</span>
          <button type="submit" disabled={sending || !text.trim()} className="btn btn-primary ml-auto sm:ml-0">
            {sending ? "Finding the right moment…" : "Make this change"}
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
                    {[e.animation && "animation", e.narration && "narration"].filter(Boolean).join(" & ")}
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
