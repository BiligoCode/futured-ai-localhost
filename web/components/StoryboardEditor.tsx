"use client";

import { useEffect, useState } from "react";

import { saveStoryboard, startRender } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Project, SceneDraft } from "@/lib/types";

import { Icon } from "./Icon";

type Draft = SceneDraft & { key: string };

let keySeq = 0;
const toDrafts = (p: Project): Draft[] =>
  p.scenes.map((s) => ({ key: s.id, id: s.id, title: s.title, visual: s.visual, narration: s.narration }));

export function StoryboardEditor({ project, onChange }: { project: Project; onChange: (p: Project) => void }) {
  const { lang, t } = useI18n();
  const timeFormat = new Intl.DateTimeFormat(lang === "el" ? "el-GR" : "en-GB", { hour: "numeric", minute: "2-digit" });
  const [drafts, setDrafts] = useState<Draft[]>(() => toDrafts(project));
  const [saving, setSaving] = useState<"save" | "render" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [removed, setRemoved] = useState<{ draft: Draft; index: number } | null>(null);

  const edit = (fn: (d: Draft[]) => Draft[]) => {
    setDrafts(fn);
    setDirty(true);
  };
  const update = (i: number, patch: Partial<Draft>) => edit((d) => d.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const move = (i: number, delta: number) =>
    edit((d) => {
      const next = [...d];
      [next[i], next[i + delta]] = [next[i + delta], next[i]];
      return next;
    });
  const remove = (i: number) => {
    setRemoved({ draft: drafts[i], index: i });
    edit((d) => d.filter((_, j) => j !== i));
  };
  const undoRemove = () => {
    if (!removed) return;
    edit((d) => [...d.slice(0, removed.index), removed.draft, ...d.slice(removed.index)]);
    setRemoved(null);
  };
  const add = () => edit((d) => [...d, { key: `new-${++keySeq}`, id: null, title: "", visual: "", narration: "" }]);

  const incomplete = drafts.length === 0 || drafts.some((d) => !d.title.trim() || !d.visual.trim() || !d.narration.trim());

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function save(): Promise<Project> {
    const payload = drafts.map(({ id, title, visual, narration }) => ({ id, title, visual, narration }));
    const saved = await saveStoryboard(project.id, payload);
    setDrafts(toDrafts(saved));
    setDirty(false);
    setRemoved(null);
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
        setSavedAt(timeFormat.format(new Date()));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-muted">{t.scriptIntro}</p>

      <ol className="panel divide-y divide-rule">
        {drafts.map((d, i) => (
          <li key={d.key} className="grid gap-4 p-5 sm:grid-cols-[3rem_minmax(0,1fr)] sm:p-6">
            <span className="font-serif text-4xl leading-none text-faint tabular-nums" aria-hidden="true">
              {i + 1}
            </span>
            <div className="min-w-0 space-y-4">
              <div className="flex items-center gap-2">
                <input
                  aria-label={t.partTitle(i + 1)}
                  value={d.title}
                  onChange={(e) => update(i, { title: e.target.value })}
                  autoComplete="off"
                  className="field -ml-2 min-w-0 border-transparent bg-transparent px-2 py-1 font-serif text-2xl font-semibold hover:border-rule focus-visible:border-accent focus-visible:bg-surface"
                  placeholder={t.partTitlePlaceholder}
                />
                <div className="flex shrink-0 gap-0.5">
                  <button type="button" className="btn-icon" onClick={() => move(i, -1)} disabled={i === 0} aria-label={t.moveUp(i + 1)}>
                    <Icon name="up" size={16} />
                  </button>
                  <button
                    type="button"
                    className="btn-icon"
                    onClick={() => move(i, 1)}
                    disabled={i === drafts.length - 1}
                    aria-label={t.moveDown(i + 1)}
                  >
                    <Icon name="down" size={16} />
                  </button>
                  <button type="button" className="btn-icon hover:!text-rec" onClick={() => remove(i)} aria-label={t.deletePart(i + 1)}>
                    <Icon name="trash" size={16} />
                  </button>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="label text-muted">{t.onScreen}</span>
                  <textarea
                    rows={4}
                    value={d.visual}
                    onChange={(e) => update(i, { visual: e.target.value })}
                    autoComplete="off"
                    className="field text-sm leading-relaxed"
                  />
                </label>
                <label className="block">
                  <span className="label text-muted">{t.narration}</span>
                  <textarea
                    rows={4}
                    value={d.narration}
                    onChange={(e) => update(i, { narration: e.target.value })}
                    autoComplete="off"
                    className="field font-serif text-base leading-relaxed"
                  />
                </label>
              </div>
            </div>
          </li>
        ))}
        <li>
          <button
            type="button"
            onClick={add}
            className="flex w-full items-center justify-center gap-2 rounded-b-[0.875rem] py-4 text-sm font-semibold text-accent hover:bg-accent-soft"
          >
            <Icon name="plus" size={16} />
            {t.addPart}
          </button>
        </li>
      </ol>

      <div aria-live="polite">
        {removed && (
          <p className="notice notice-info items-center">
            <span className="flex-1">{t.removedPart(removed.draft.title || t.untitledPart)}</span>
            <button type="button" onClick={undoRemove} className="font-semibold underline underline-offset-2">
              {t.undo}
            </button>
          </p>
        )}
        {error && (
          <p className="notice notice-error mt-2" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center justify-end gap-3 border-t border-rule bg-paper/95 px-4 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur sm:-mx-6 sm:px-6">
        <span className="mr-auto text-sm" aria-live="polite">
          {incomplete ? (
            <span className="text-gold-ink">{t.incompleteParts}</span>
          ) : dirty ? (
            <span className="text-muted">{t.unsaved}</span>
          ) : (
            savedAt && <span className="text-muted">{t.savedAt(savedAt)}</span>
          )}
        </span>
        <button type="button" onClick={() => run("save")} disabled={!!saving || incomplete} className="btn btn-secondary">
          {saving === "save" ? t.saving : t.save}
        </button>
        <button type="button" onClick={() => run("render")} disabled={!!saving || incomplete} className="btn btn-primary">
          {saving === "render" ? t.starting : t.approve}
        </button>
      </div>
    </div>
  );
}
