"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Icon } from "@/components/Icon";
import { Stepper } from "@/components/Stepper";
import { createProject } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const LANGUAGES = [
  { value: "el", label: "Ελληνικά", lang: "el" },
  { value: "en", label: "English", lang: "en" },
] as const;

/** A row of radio buttons that reads as a segmented control. */
function Segmented({ name, legend, options, defaultValue, hint }: {
  name: string;
  legend: string;
  options: readonly { value: string; label: string; lang?: string }[];
  defaultValue: string;
  hint?: string;
}) {
  return (
    <fieldset>
      <legend className="label">{legend}</legend>
      {hint && <p className="hint -mt-1 mb-2">{hint}</p>}
      <div className="grid auto-cols-fr grid-flow-col gap-1 rounded-lg bg-sunken p-1">
        {options.map((o) => (
          <label key={o.value} className="cursor-pointer" lang={o.lang}>
            <input type="radio" name={name} value={o.value} defaultChecked={o.value === defaultValue} className="peer sr-only" />
            <span className="block rounded-md px-3 py-2 text-center text-sm text-muted transition-colors peer-checked:bg-surface peer-checked:font-semibold peer-checked:text-ink peer-checked:shadow-[0_1px_2px_rgb(15_20_27/0.12)] peer-focus-visible:outline-2 peer-focus-visible:outline-accent hover:text-ink">
              {o.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function NewProject() {
  const { lang, t } = useI18n();
  const router = useRouter();
  const durations = (["short", "medium", "long"] as const).map((value) => ({ value, label: t.durations[value] }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);

  function addFiles(input: HTMLInputElement) {
    const picked = Array.from(input.files ?? []);
    // Reset so picking the same file again after removing it still fires onChange.
    input.value = "";
    setFiles((prev) => [
      ...prev,
      ...picked.filter((f) => !prev.some((p) => p.name === f.name && p.size === f.size)),
    ]);
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    form.delete("files");
    for (const f of files) form.append("files", f);
    try {
      const project = await createProject(form);
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-8">
      <Stepper current={1} />
      <div className="max-w-2xl">
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight">{t.newTitle}</h1>
        <p className="mt-2 text-lg text-muted">{t.newSubtitle}</p>
      </div>

      <form onSubmit={onSubmit} className="panel grid overflow-hidden lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
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
              className="field font-serif text-2xl leading-snug"
              placeholder={t.conceptPlaceholder}
            />
          </div>

          <div>
            <span className="label">{t.notesLabel}</span>
            <label className="group flex cursor-pointer items-center gap-4 rounded-lg border border-dashed border-rule-strong bg-paper px-4 py-4 transition-colors hover:border-accent focus-within:border-accent focus-within:outline-2 focus-within:outline-accent">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-surface text-accent ring-1 ring-rule">
                <Icon name="file" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-ink">
                  {files.length ? t.addMorePdfs : t.choosePdfs}
                </span>
                <span className="hint block">{t.pdfHint}</span>
              </span>
              <input
                name="files"
                type="file"
                accept="application/pdf"
                multiple
                className="sr-only"
                onChange={(e) => addFiles(e.currentTarget)}
              />
            </label>
            {files.length > 0 && (
              <ul className="mt-2 space-y-1">
                {files.map((f, i) => (
                  <li key={`${f.name}-${f.size}`} className="flex items-center gap-2 rounded-md bg-sunken px-3 py-1.5 text-sm">
                    <Icon name="file" size={16} className="shrink-0 text-accent" />
                    <span className="min-w-0 flex-1 truncate">{f.name}</span>
                    <button
                      type="button"
                      aria-label={t.removeFile(f.name)}
                      className="text-muted hover:text-ink"
                      onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                    >
                      <Icon name="close" size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <label htmlFor="material_text" className="label">
              {t.pasteLabel}
            </label>
            <textarea
              id="material_text"
              name="material_text"
              rows={6}
              autoComplete="off"
              className="field"
              placeholder={t.pastePlaceholder}
            />
          </div>
        </div>

        <div className="flex flex-col gap-6 border-t border-rule bg-paper/60 p-6 sm:p-8 lg:border-t-0 lg:border-l">
          <Segmented name="language" legend={t.videoLanguage} hint={t.videoLanguageHint} options={LANGUAGES} defaultValue={lang} />
          <div>
            <label htmlFor="style" className="label">
              {t.styleLabel}
            </label>
            <textarea
              id="style"
              name="style"
              rows={3}
              autoComplete="off"
              className="field"
              placeholder={t.stylePlaceholder}
            />
          </div>
          <Segmented name="duration" legend={t.videoLength} options={durations} defaultValue="medium" />

          <div className="mt-auto space-y-3 pt-2">
            {error && (
              <p className="notice notice-error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" disabled={submitting} className="btn btn-primary w-full py-3 disabled:cursor-wait">
              {submitting ? t.drafting : t.draftScript}
            </button>
            <p className="hint text-center">{t.nothingAnimated}</p>
          </div>
        </div>
      </form>
    </div>
  );
}
