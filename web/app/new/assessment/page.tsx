"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PaperDrop } from "@/components/assess/PaperDrop";
import { Icon } from "@/components/Icon";
import { LANGUAGES, Segmented } from "@/components/Segmented";
import { createAssessment } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { mergeFiles, type UploadOutcome, uploadInBatches } from "@/lib/upload";

export default function NewAssessment() {
  const { lang, t } = useI18n();
  const router = useRouter();
  const [exam, setExam] = useState<File[]>([]);
  const [papers, setPapers] = useState<File[]>([]);
  const [split, setSplit] = useState(false);
  const [splitEvery, setSplitEvery] = useState(4);
  const [phase, setPhase] = useState<"form" | "creating" | "uploading" | "done">("form");
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<{ id: string; result: UploadOutcome } | null>(null);
  const busy = phase === "creating" || phase === "uploading";

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setPhase("creating");
    const form = new FormData(e.currentTarget);
    form.delete("exam_files");
    form.delete("papers");
    for (const f of exam) form.append("exam_files", f, f.name);
    let id: string;
    try {
      id = (await createAssessment(form)).id;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase("form");
      return;
    }
    if (!papers.length) {
      router.push(`/assessments/${id}`);
      return;
    }
    setPhase("uploading");
    const result = await uploadInBatches(id, papers, split ? splitEvery : null, (done, total) => setProgress({ done, total }));
    if (!result.skipped.length && !result.failed.length) {
      router.push(`/assessments/${id}`);
      return;
    }
    setOutcome({ id, result });
    setPhase("done");
  }

  if (outcome) {
    const { id, result } = outcome;
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight">{t.asm.newTitle}</h1>
        {result.added > 0 && <p className="notice notice-info">{t.asm.papersAdded(result.added)}</p>}
        {result.error && (
          <p className="notice notice-error" role="alert">
            {result.error}
          </p>
        )}
        {(result.skipped.length > 0 || result.failed.length > 0) && (
          <div className="panel p-5">
            <h2 className="font-semibold">{t.asm.skippedTitle}</h2>
            <ul className="mt-3 space-y-1.5 text-sm">
              {result.skipped.map((s, i) => (
                <li key={`${s.filename}-${i}`} className="flex gap-2">
                  <Icon name="alert" size={16} className="mt-0.5 shrink-0 text-warn" />
                  <span>
                    <span className="font-medium">{s.filename}</span> — <span className="text-muted">{s.reason}</span>
                  </span>
                </li>
              ))}
              {result.failed.map((f) => (
                <li key={f.name} className="flex gap-2">
                  <Icon name="alert" size={16} className="mt-0.5 shrink-0 text-critical" />
                  <span className="font-medium">{f.name}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <button type="button" className="btn btn-primary" onClick={() => router.push(`/assessments/${id}`)}>
          {t.asm.continue}
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="max-w-2xl">
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight">{t.asm.newTitle}</h1>
        <p className="mt-2 text-lg text-muted">{t.asm.newSubtitle}</p>
      </div>

      <form onSubmit={onSubmit} className="panel grid overflow-hidden lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <fieldset disabled={busy} className="min-w-0 space-y-6 p-6 sm:p-8">
          <div>
            <label htmlFor="title" className="label">
              {t.asm.titleLabel}
            </label>
            <input id="title" name="title" required autoComplete="off" className="field font-serif text-2xl leading-snug" placeholder={t.asm.titlePlaceholder} />
          </div>
          <div>
            <label htmlFor="course" className="label">
              {t.asm.courseLabel}
            </label>
            <input id="course" name="course" autoComplete="off" className="field" placeholder={t.asm.coursePlaceholder} />
          </div>

          <div>
            <span className="label">{t.asm.examLabel}</span>
            <p className="hint -mt-1 mb-2">{t.asm.examHint}</p>
            <label className="group flex cursor-pointer items-center gap-4 rounded-lg border border-dashed border-rule-strong bg-paper px-4 py-3 transition-colors hover:border-accent focus-within:border-accent focus-within:outline-2 focus-within:outline-accent">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-surface text-accent ring-1 ring-rule">
                <Icon name="exam" />
              </span>
              <span className="min-w-0 flex-1 text-sm font-semibold text-ink">{t.asm.chooseExam}</span>
              <input
                name="exam_files"
                type="file"
                multiple
                accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png"
                className="sr-only"
                onChange={(e) => {
                  const picked = Array.from(e.currentTarget.files ?? []);
                  e.currentTarget.value = "";
                  setExam((cur) => mergeFiles(cur, picked));
                }}
              />
            </label>
            {exam.length > 0 && (
              <ul className="mt-2 space-y-1">
                {exam.map((f) => (
                  <li key={`${f.name}|${f.size}`} className="flex items-center gap-2 rounded-md bg-sunken px-3 py-1.5 text-sm">
                    <Icon name="file" size={16} className="shrink-0 text-accent" />
                    <span className="min-w-0 flex-1 truncate">{f.name}</span>
                    <button type="button" aria-label={t.asm.removeFile(f.name)} className="text-muted hover:text-ink" onClick={() => setExam(exam.filter((x) => x !== f))}>
                      <Icon name="close" size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <label htmlFor="exam_text" className="label">
              {t.asm.examPasteLabel}
            </label>
            <textarea id="exam_text" name="exam_text" rows={5} className="field" placeholder={t.asm.examPastePlaceholder} />
          </div>
          <div>
            <label htmlFor="instructions" className="label">
              {t.asm.instructionsLabel}
            </label>
            <textarea id="instructions" name="instructions" rows={3} className="field" placeholder={t.asm.instructionsPlaceholder} />
          </div>
        </fieldset>

        <fieldset disabled={busy} className="flex min-w-0 flex-col gap-6 border-t border-rule bg-paper/60 p-6 sm:p-8 lg:border-t-0 lg:border-l">
          <Segmented name="language" legend={t.asm.languageLabel} hint={t.asm.languageHint} options={LANGUAGES} defaultValue={lang} />
          <Segmented
            name="scale"
            legend={t.asm.scaleLabel}
            options={[10, 20, 100].map((v) => ({ value: String(v), label: t.asm.scales[v] }))}
            defaultValue={lang === "el" ? "10" : "100"}
          />
          <div>
            <span className="label">{t.asm.papersLabel}</span>
            <PaperDrop files={papers} onFiles={setPapers} />
            <label className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <input type="checkbox" checked={split} onChange={(e) => setSplit(e.currentTarget.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />
              <span>{t.asm.splitLabel}</span>
              <input
                type="number"
                min={1}
                max={40}
                value={splitEvery}
                disabled={!split}
                onChange={(e) => setSplitEvery(Math.max(1, Math.min(40, Number(e.currentTarget.value) || 1)))}
                aria-label={`${t.asm.splitLabel} (${t.asm.splitPages})`}
                className="field w-16 px-2 py-1 text-center tabular-nums"
              />
              <span>{t.asm.splitPages}</span>
            </label>
          </div>
          <div className="mt-auto space-y-3 pt-2">
            {error && (
              <p className="notice notice-error" role="alert">
                {error}
              </p>
            )}
            {phase === "uploading" && (
              <div aria-live="polite" className="space-y-1.5">
                <p className="text-sm text-muted tabular-nums">{t.asm.uploading(progress.done, progress.total)}</p>
                <div className="h-1.5 overflow-hidden rounded-full bg-sunken">
                  <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} />
                </div>
              </div>
            )}
            <button type="submit" disabled={busy} className="btn btn-primary w-full py-3 disabled:cursor-wait">
              {phase === "creating" ? t.asm.creating : phase === "uploading" ? t.asm.uploading(progress.done, progress.total) : t.asm.create}
            </button>
            <p className="hint text-center">{papers.length ? t.asm.startHint : t.asm.noPapersYet}</p>
          </div>
        </fieldset>
      </form>
    </div>
  );
}
