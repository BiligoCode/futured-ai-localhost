"use client";

import { useState } from "react";

import { saveStoryboard, startRender } from "@/lib/api";
import type { Project, SceneDraft } from "@/lib/types";

const field = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none";
const iconBtn = "rounded-md border border-slate-200 px-2 py-1 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-30";

type Draft = SceneDraft & { key: string };

let keySeq = 0;
const toDrafts = (p: Project): Draft[] =>
  p.scenes.map((s) => ({ key: s.id, id: s.id, title: s.title, visual: s.visual, narration: s.narration }));

export function StoryboardEditor({ project, onChange }: { project: Project; onChange: (p: Project) => void }) {
  const [drafts, setDrafts] = useState<Draft[]>(() => toDrafts(project));
  const [saving, setSaving] = useState<"save" | "render" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const update = (i: number, patch: Partial<Draft>) =>
    setDrafts((d) => d.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const move = (i: number, delta: number) =>
    setDrafts((d) => {
      const next = [...d];
      [next[i], next[i + delta]] = [next[i + delta], next[i]];
      return next;
    });
  const remove = (i: number) => setDrafts((d) => d.filter((_, j) => j !== i));
  const add = () =>
    setDrafts((d) => [...d, { key: `new-${++keySeq}`, id: null, title: "", visual: "", narration: "" }]);

  const incomplete = drafts.length === 0 || drafts.some((d) => !d.title.trim() || !d.visual.trim() || !d.narration.trim());

  async function save(): Promise<Project> {
    const payload = drafts.map(({ id, title, visual, narration }) => ({ id, title, visual, narration }));
    const saved = await saveStoryboard(project.id, payload);
    setDrafts(toDrafts(saved));
    return saved;
  }

  async function run(kind: "save" | "render") {
    setSaving(kind);
    setError(null);
    try {
      const saved = await save();
      if (kind === "render") {
        onChange(await startRender(project.id));
      } else {
        onChange(saved);
        setSavedAt(new Date().toLocaleTimeString());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-slate-600">
        Review the AI&apos;s storyboard. Edit what appears on screen and what is said, reorder or remove scenes. Nothing is rendered until you approve.
      </p>

      <ol className="space-y-4">
        {drafts.map((d, i) => (
          <li key={d.key} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-3">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-700">{i + 1}</span>
              <input
                aria-label={`Scene ${i + 1} title`}
                value={d.title}
                onChange={(e) => update(i, { title: e.target.value })}
                className={field + " font-medium"}
                placeholder="Scene title"
              />
              <div className="flex shrink-0 gap-1">
                <button type="button" className={iconBtn} onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up">↑</button>
                <button type="button" className={iconBtn} onClick={() => move(i, 1)} disabled={i === drafts.length - 1} aria-label="Move down">↓</button>
                <button type="button" className={iconBtn + " hover:text-red-600"} onClick={() => remove(i)} aria-label="Delete scene">✕</button>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">On screen</span>
                <textarea rows={4} value={d.visual} onChange={(e) => update(i, { visual: e.target.value })} className={field} />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Narration</span>
                <textarea rows={4} value={d.narration} onChange={(e) => update(i, { narration: e.target.value })} className={field} />
              </label>
            </div>
          </li>
        ))}
      </ol>

      <button type="button" onClick={add} className="w-full rounded-xl border border-dashed border-slate-300 py-3 text-sm text-slate-600 hover:bg-white">
        + Add scene
      </button>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <div className="sticky bottom-0 flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50/95 py-4">
        {savedAt && <span className="text-sm text-slate-500">Saved at {savedAt}</span>}
        {incomplete && <span className="text-sm text-amber-700">Every scene needs a title, visual and narration.</span>}
        <button type="button" onClick={() => run("save")} disabled={!!saving || incomplete} className="rounded-lg border border-slate-300 bg-white px-4 py-2 font-medium hover:bg-slate-100 disabled:opacity-50">
          {saving === "save" ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={() => run("render")} disabled={!!saving || incomplete} className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {saving === "render" ? "Starting…" : "Approve & render"}
        </button>
      </div>
    </div>
  );
}
