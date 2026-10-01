"use client";

import { useState } from "react";

import { reviseVideo } from "@/lib/api";
import { clock } from "@/lib/time";
import type { CutKind, EditSummary, Project } from "@/lib/types";

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
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h2 className="font-semibold">Ask for a change</h2>
        <p className="text-sm text-slate-600">
          Describe it the way you would to a colleague: what happens on screen, what is said, or a time in the video. Lara finds the right moment and changes only that.
        </p>
      </div>
      <form onSubmit={submit} className="space-y-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          disabled={sending}
          aria-label="Describe a change to the video"
          placeholder={"e.g. “When the array gets iterated, move the pointer more slowly”\nor “At 0:32 explain why we split the array in half”"}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          {playerAt !== null && (
            <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
              📍 At {clock(playerAt)} in the video
              <button type="button" onClick={onClearPlayerAt} className="ml-1 text-indigo-400 hover:text-indigo-700" aria-label="Don't use the player position">✕</button>
            </span>
          )}
          <span className="flex-1" />
          <button type="submit" disabled={sending || !text.trim()} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40">
            {sending ? "Finding the right moment…" : "Make this change"}
          </button>
        </div>
      </form>
      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {planned && (
        <ul className="space-y-1 rounded-lg bg-slate-50 p-3 text-sm">
          {planned.map((e) => (
            <li key={e.scene_id} className="flex gap-2">
              <span className="shrink-0 font-mono text-xs leading-5 text-indigo-700">
                {e.start !== null && e.end !== null ? `${clock(e.start)}–${clock(e.end)}` : "—"}
              </span>
              <span>
                {e.summary}
                <span className="ml-2 text-xs text-slate-500">
                  {[e.animation && "animation", e.narration && "narration"].filter(Boolean).join(" + ")}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
