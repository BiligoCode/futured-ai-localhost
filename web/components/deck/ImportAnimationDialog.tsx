"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { listProjects } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { clock } from "@/lib/time";
import type { EmbedMode, Project } from "@/lib/types";
import { useDialogKeys } from "@/lib/useDialogKeys";

import { EmbedModePicker } from "./EmbedModePicker";

const ready = (p: Project) => p.stage === "scenes" && p.preview.version > 0;
const length = (p: Project) => (p.final.version > 0 ? p.final : p.preview).duration;

/** "Import animation": put any finished animation (from these slides or not) on the current slide or a new one. */
export function ImportAnimationDialog({ activeLabel, activeHasVideo, onImport, onClose }: {
  activeLabel: string | null;
  activeHasVideo: boolean;
  onImport: (projectId: string, mode: EmbedMode) => Promise<void>;
  onClose: () => void;
}) {
  const { t, lang } = useI18n();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [mode, setMode] = useState<EmbedMode>(activeLabel ? "new_after" : "new_end");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((all) => {
        if (cancelled) return;
        const finished = all.filter(ready).sort((a, b) => b.created_at.localeCompare(a.created_at));
        setProjects(finished);
        setChosen(finished[0]?.id ?? null);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  useDialogKeys(dialog, onClose);

  async function confirm() {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    try {
      await onImport(chosen, mode);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const needsSlide = mode !== "new_end";
  const date = new Intl.DateTimeFormat(lang === "el" ? "el-GR" : "en-GB", { day: "numeric", month: "short", year: "numeric" });

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-stage/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
        onClick={(e) => e.stopPropagation()}
        className="panel flex max-h-[90dvh] w-full max-w-2xl flex-col overflow-hidden shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-rule px-6 py-4">
          <div>
            <h2 id="import-title" className="font-serif text-2xl font-semibold">
              {t.importTitle}
            </h2>
            <p className="mt-0.5 text-sm text-muted">{t.importHint}</p>
          </div>
          <button type="button" onClick={onClose} className="btn-icon" aria-label={t.close}>
            <Icon name="close" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {!projects && !error && <p className="text-sm text-muted">{t.loading}</p>}
          {projects?.length === 0 && <p className="text-sm text-muted">{t.importEmpty}</p>}
          {projects && projects.length > 0 && (
            <fieldset disabled={busy}>
              <legend className="sr-only">{t.importTitle}</legend>
              <ul className="space-y-1.5">
                {projects.map((p) => (
                  <li key={p.id}>
                    <label className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors ${chosen === p.id ? "border-accent bg-sunken" : "border-rule hover:border-rule-strong"}`}>
                      <input type="radio" name="animation" value={p.id} checked={chosen === p.id} onChange={() => setChosen(p.id)} className="accent-accent" />
                      <Icon name="film" size={18} className="shrink-0 text-muted" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{p.title}</span>
                        <span className="block text-xs text-muted">
                          {clock(length(p))} · {date.format(new Date(p.created_at))}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          )}
          {error && (
            <p className="notice notice-error mt-4" role="alert">
              {error}
            </p>
          )}
        </div>

        <div className="space-y-3 border-t border-rule bg-paper/60 px-6 py-4">
          {activeLabel && <p className="text-sm text-muted">{t.importCurrentSlide(activeLabel)}</p>}
          <EmbedModePicker mode={mode} onChange={setMode} />
          {mode === "append" && activeHasVideo && <p className="notice notice-warn">{t.embedReplaces}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="btn btn-ghost">
              {t.cancel}
            </button>
            <button type="button" onClick={() => void confirm()} disabled={busy || !chosen || (needsSlide && !activeLabel)} className="btn btn-primary">
              {busy ? t.adding : t.embedConfirm}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
