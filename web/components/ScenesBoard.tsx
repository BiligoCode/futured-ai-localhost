"use client";

import type { Project } from "@/lib/types";

import { SceneCard } from "./SceneCard";

export function ScenesBoard({ project, onChange, onContinue }: {
  project: Project;
  onChange: (p: Project) => void;
  onContinue: () => void;
}) {
  const ready = project.scenes.filter((s) => s.render_status === "done").length;
  const total = project.scenes.length;
  const allReady = ready === total;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-64 flex-1">
          <p className="mb-1 text-sm font-medium">
            {ready} of {total} scenes ready
          </p>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full bg-indigo-600 transition-all" style={{ width: `${(ready / total) * 100}%` }} />
          </div>
        </div>
        <button type="button" onClick={onContinue} disabled={!allReady} className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-40">
          Continue to voice →
        </button>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {project.scenes.map((s, i) => (
          <SceneCard key={s.id} project={project} scene={s} index={i} onChange={onChange} />
        ))}
      </div>
    </div>
  );
}
