"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { MaterialFields } from "@/components/MaterialFields";
import { LANGUAGES, Segmented } from "@/components/Segmented";
import { Stepper } from "@/components/Stepper";
import { createProject, getMaterial, getProject } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Project } from "@/lib/types";

/** Back to setup from an existing video: its settings and material, to change and redraft. */
type Source = { project: Project; material: string };

export default function NewProject() {
  return (
    <Suspense fallback={null}>
      <SetupLoader />
    </Suspense>
  );
}

function SetupLoader() {
  const { t } = useI18n();
  const from = useSearchParams().get("from");
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!from) return;
    let cancelled = false;
    Promise.all([getProject(from), getMaterial(from)])
      .then(([project, material]) => !cancelled && setSource({ project, material }))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [from]);

  if (from && error)
    return (
      <p className="notice notice-error" role="alert">
        {error}
      </p>
    );
  if (from && !source)
    return (
      <p className="text-muted" aria-live="polite">
        {t.loading}
      </p>
    );
  return <SetupForm key={source?.project.id ?? "new"} source={from ? source : null} />;
}

function SetupForm({ source }: { source: Source | null }) {
  const { lang, t } = useI18n();
  const router = useRouter();
  const durations = (["short", "medium", "long"] as const).map((value) => ({ value, label: t.durations[value] }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const drafting = useRef<AbortController | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    form.delete("files");
    for (const f of files) form.append("files", f);
    const controller = new AbortController();
    drafting.current = controller;
    try {
      const project = await createProject(form, controller.signal);
      router.push(`/projects/${project.id}`);
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <Stepper current={1} go={source ? { 2: `/projects/${source.project.id}` } : undefined} />
      <div className="max-w-2xl">
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight">
          {source ? t.changeSetupTitle : t.newTitle}
        </h1>
        <p className="mt-2 text-lg text-muted">{source ? t.changeSetupSubtitle : t.newSubtitle}</p>
      </div>

      <form onSubmit={onSubmit} className="panel grid overflow-hidden lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        {source && <input type="hidden" name="replaces" value={source.project.id} />}
        <div className="space-y-6 p-6 sm:p-8">
          <div>
            <label htmlFor="concept" className="label">
              {t.conceptLabel}
            </label>
            <input
              id="concept"
              name="concept"
              required
              autoComplete="off"
              defaultValue={source?.project.concept}
              className="field font-serif text-2xl leading-snug"
              placeholder={t.conceptPlaceholder}
            />
          </div>

          <MaterialFields files={files} onFiles={setFiles} defaultText={source?.material} />
        </div>

        <div className="flex flex-col gap-6 border-t border-rule bg-paper/60 p-6 sm:p-8 lg:border-t-0 lg:border-l">
          <Segmented name="language" legend={t.videoLanguage} hint={t.videoLanguageHint} options={LANGUAGES} defaultValue={source?.project.language ?? lang} />
          <div>
            <label htmlFor="style" className="label">
              {t.styleLabel}
            </label>
            <textarea
              id="style"
              name="style"
              rows={3}
              autoComplete="off"
              defaultValue={source?.project.style}
              className="field"
              placeholder={t.stylePlaceholder}
            />
          </div>
          <Segmented name="duration" legend={t.videoLength} options={durations} defaultValue={source?.project.duration ?? "medium"} />

          <div className="mt-auto space-y-3 pt-2">
            {error && (
              <p className="notice notice-error" role="alert">
                {error}
              </p>
            )}
            {source && <p className="notice notice-warn">{t.redraftWarning}</p>}
            <button type="submit" disabled={submitting} className="btn btn-primary w-full py-3 disabled:cursor-wait">
              {submitting ? t.drafting : source ? t.redraftScript : t.draftScript}
            </button>
            {submitting && (
              <button type="button" onClick={() => drafting.current?.abort()} className="btn btn-ghost w-full">
                {t.cancel}
              </button>
            )}
            {source && !submitting ? (
              <button type="button" onClick={() => router.push(`/projects/${source.project.id}`)} className="btn btn-ghost w-full">
                {t.keepScript}
              </button>
            ) : (
              <p className="hint text-center">{t.nothingAnimated}</p>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
