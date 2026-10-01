"use client";

import { useState } from "react";

import { exportProject, exportUrl } from "@/lib/api";
import type { Project } from "@/lib/types";

import { ScenePreview } from "./ScenePreview";

export function ExportPanel({ project }: { project: Project }) {
  const [exporting, setExporting] = useState(false);
  const [exportedAt, setExportedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const allRendered = project.scenes.every((s) => s.render_status === "done");
  const silent = project.scenes.map((s, i) => ({ s, i })).filter(({ s }) => s.audio_status !== "done");

  async function run() {
    setExporting(true);
    setError(null);
    try {
      await exportProject(project.id);
      setExportedAt(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="space-y-4 rounded-xl border border-indigo-200 bg-indigo-50/50 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Export</h2>
          <p className="text-sm text-slate-600">
            {silent.length === 0
              ? "Every scene has a voice. Each scene waits for its narration to finish."
              : `Scene${silent.length > 1 ? "s" : ""} ${silent.map(({ i }) => i + 1).join(", ")} ha${silent.length > 1 ? "ve" : "s"} no voice and will be silent.`}
          </p>
        </div>
        <button type="button" onClick={run} disabled={!allRendered || exporting} className="rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white hover:bg-indigo-700 disabled:opacity-40">
          {exporting ? "Exporting…" : exportedAt ? "Export again" : "Export video"}
        </button>
      </div>
      {!allRendered && <p className="text-sm text-amber-700">All scenes must be rendered before export.</p>}
      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {exportedAt && (
        <div className="space-y-3">
          <ScenePreview key={exportedAt} src={exportUrl(project.id, exportedAt)} className="aspect-video w-full rounded-lg bg-black" />
          <a href={exportUrl(project.id, exportedAt)} download className="inline-block rounded-lg border border-indigo-300 bg-white px-4 py-2 font-medium text-indigo-700 hover:bg-indigo-50">
            ⬇ Download MP4
          </a>
        </div>
      )}
    </section>
  );
}
