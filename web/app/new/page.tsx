"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Stepper } from "@/components/Stepper";
import { createProject } from "@/lib/api";

const field = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 focus:border-indigo-500 focus:outline-none";

export default function NewProject() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    <div className="space-y-6">
      <Stepper current={1} />
      <div>
        <h1 className="text-2xl font-semibold">New visual explanation</h1>
        <p className="text-slate-600">Give us your course material and the concept. We draft a storyboard you can edit before anything is rendered.</p>
      </div>

      <form onSubmit={onSubmit} className="grid gap-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:grid-cols-2">
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block font-medium">Concept to explain *</span>
            <input name="concept" required className={field} placeholder="e.g. Κάθοδος κλίσης (gradient descent)" />
          </label>
          <label className="block">
            <span className="mb-1 block font-medium">Lecture notes or slides (PDF)</span>
            <input name="file" type="file" accept="application/pdf" className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-indigo-700" />
          </label>
          <label className="block">
            <span className="mb-1 block font-medium">…or paste course material</span>
            <textarea name="material_text" rows={6} className={field} placeholder="Definitions, notation, examples from your course" />
          </label>
        </div>
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block font-medium">Language</span>
            <select name="language" defaultValue="el" className={field}>
              <option value="el">Ελληνικά</option>
              <option value="en">English</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block font-medium">Visual style</span>
            <input name="style" className={field} placeholder="e.g. minimal, geometric, step by step" />
          </label>
          <label className="block">
            <span className="mb-1 block font-medium">Tone</span>
            <input name="tone" className={field} placeholder="e.g. friendly, rigorous, for first-year students" />
          </label>
          {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-medium text-white hover:bg-indigo-700 disabled:cursor-wait disabled:opacity-70"
          >
            {submitting ? "Reading your material and drafting a storyboard…" : "Draft storyboard"}
          </button>
        </div>
      </form>
    </div>
  );
}
