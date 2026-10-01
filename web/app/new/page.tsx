"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Icon } from "@/components/Icon";
import { Stepper } from "@/components/Stepper";
import { createProject } from "@/lib/api";

const DURATIONS = [
  { value: "short", label: "Under 1 min" },
  { value: "medium", label: "1–3 min" },
  { value: "long", label: "3–5 min" },
] as const;

const LANGUAGES = [
  { value: "el", label: "Ελληνικά", lang: "el" },
  { value: "en", label: "English", lang: "en" },
] as const;

/** A row of radio buttons that reads as a segmented control. */
function Segmented({ name, legend, options, defaultValue }: {
  name: string;
  legend: string;
  options: readonly { value: string; label: string; lang?: string }[];
  defaultValue: string;
}) {
  return (
    <fieldset>
      <legend className="label">{legend}</legend>
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
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    const file = form.get("file");
    if (file instanceof File && file.size === 0) form.delete("file");
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
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight">New visual explanation</h1>
        <p className="mt-2 text-lg text-muted">
          Give Lara your course material and the concept. It drafts a script you can edit before anything is animated.
        </p>
      </div>

      <form onSubmit={onSubmit} className="panel grid overflow-hidden lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="space-y-6 p-6 sm:p-8">
          <div>
            <label htmlFor="concept" className="label">
              Concept to explain
            </label>
            <input
              id="concept"
              name="concept"
              required
              autoComplete="off"
              className="field font-serif text-2xl leading-snug"
              placeholder="e.g. Κάθοδος κλίσης (gradient descent)…"
            />
          </div>

          <div>
            <span className="label">Lecture notes or slides</span>
            <label className="group flex cursor-pointer items-center gap-4 rounded-lg border border-dashed border-rule-strong bg-paper px-4 py-4 transition-colors hover:border-accent focus-within:border-accent focus-within:outline-2 focus-within:outline-accent">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-surface text-accent ring-1 ring-rule">
                <Icon name="file" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-ink">{fileName ?? "Choose a PDF"}</span>
                <span className="hint block">{fileName ? "Click to choose a different file" : "Optional. Lara reads the notation and examples from it."}</span>
              </span>
              <input
                name="file"
                type="file"
                accept="application/pdf"
                className="sr-only"
                onChange={(e) => setFileName(e.currentTarget.files?.[0]?.name ?? null)}
              />
            </label>
          </div>

          <div>
            <label htmlFor="material_text" className="label">
              Or paste course material
            </label>
            <textarea
              id="material_text"
              name="material_text"
              rows={6}
              autoComplete="off"
              className="field"
              placeholder="Definitions, notation, examples from your course…"
            />
          </div>
        </div>

        <div className="flex flex-col gap-6 border-t border-rule bg-paper/60 p-6 sm:p-8 lg:border-t-0 lg:border-l">
          <Segmented name="language" legend="Language" options={LANGUAGES} defaultValue="el" />
          <div>
            <label htmlFor="style" className="label">
              Style &amp; tone
            </label>
            <textarea
              id="style"
              name="style"
              rows={3}
              autoComplete="off"
              className="field"
              placeholder="e.g. minimal and step by step, friendly, for first-year students…"
            />
          </div>
          <Segmented name="duration" legend="Video length" options={DURATIONS} defaultValue="medium" />

          <div className="mt-auto space-y-3 pt-2">
            {error && (
              <p className="notice notice-error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" disabled={submitting} className="btn btn-primary w-full py-3 disabled:cursor-wait">
              {submitting ? "Reading your material and drafting a script…" : "Draft script"}
            </button>
            <p className="hint text-center">Nothing is animated until you approve the script.</p>
          </div>
        </div>
      </form>
    </div>
  );
}
