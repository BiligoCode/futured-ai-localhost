"use client";

import { useState } from "react";

import { getSceneCode, retryScene, reviseScene, videoUrl } from "@/lib/api";
import type { Project, Scene } from "@/lib/types";

import { ScenePreview } from "./ScenePreview";

const MAX_ATTEMPTS = 4;
const BUSY = new Set(["generating", "rendering", "repairing"]);

function statusBadge(scene: Scene): { label: string; className: string } {
  const attempt = `attempt ${Math.max(scene.attempts, 1)} of ${MAX_ATTEMPTS}`;
  switch (scene.render_status) {
    case "pending":
      return { label: "Pending", className: "bg-slate-100 text-slate-600" };
    case "generating":
      return { label: "Writing animation code…", className: "bg-indigo-50 text-indigo-700 animate-pulse" };
    case "rendering":
      return { label: `Rendering (${attempt})`, className: "bg-indigo-50 text-indigo-700 animate-pulse" };
    case "repairing":
      return { label: `Fixing an error (${attempt})`, className: "bg-amber-50 text-amber-700 animate-pulse" };
    case "done":
      return { label: "Ready", className: "bg-emerald-50 text-emerald-700" };
    case "failed":
      return { label: "Failed", className: "bg-red-50 text-red-700" };
  }
}

export function SceneCard({ project, scene, index, onChange }: {
  project: Project;
  scene: Scene;
  index: number;
  onChange: (p: Project) => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [code, setCode] = useState<string | null>(null);
  const [showCode, setShowCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = BUSY.has(scene.render_status);
  const badge = statusBadge(scene);

  async function act(fn: () => Promise<Project>) {
    setError(null);
    try {
      onChange(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function toggleCode() {
    if (!showCode) {
      try {
        setCode(await getSceneCode(project.id, scene.id));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return;
      }
    }
    setShowCode(!showCode);
  }

  return (
    <article className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="relative aspect-video bg-slate-900">
        {scene.code_version > 0 ? (
          <ScenePreview key={scene.code_version} src={videoUrl(project.id, scene.id, scene.code_version)} className="h-full w-full" />
        ) : (
          <div className="grid h-full place-items-center text-sm text-slate-400">
            {busy ? "The AI is building this scene…" : scene.render_status === "failed" ? "No video yet" : "Waiting to start"}
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold">
            <span className="mr-1 text-slate-400">{index + 1}.</span>
            {scene.title}
          </h3>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>{badge.label}</span>
        </div>
        <p className="text-sm text-slate-600">{scene.narration}</p>

        {scene.render_status === "done" && scene.last_error && (
          <details className="rounded-lg bg-amber-50 p-3 text-sm">
            <summary className="cursor-pointer text-amber-800">The last change could not be applied. Previous version kept.</summary>
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-xs text-amber-900">{scene.last_error}</pre>
          </details>
        )}

        {scene.render_status === "failed" && (
          <div className="space-y-2 rounded-lg bg-red-50 p-3 text-sm">
            {scene.last_error && (
              <details>
                <summary className="cursor-pointer text-red-700">Show error</summary>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-xs text-red-900">{scene.last_error}</pre>
              </details>
            )}
            <button type="button" onClick={() => act(() => retryScene(project.id, scene.id))} className="rounded-md bg-red-600 px-3 py-1 font-medium text-white hover:bg-red-700">
              Retry
            </button>
          </div>
        )}

        <form
          className="mt-auto flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!instruction.trim()) return;
            act(() => reviseScene(project.id, scene.id, instruction.trim())).then(() => setInstruction(""));
          }}
        >
          <input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            disabled={busy || scene.code_version === 0}
            placeholder="Ask for a change, e.g. “make the arrow red”"
            aria-label={`Revise scene ${index + 1}`}
            className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
          />
          <button type="submit" disabled={busy || scene.code_version === 0 || !instruction.trim()} className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40">
            Revise
          </button>
        </form>

        {scene.code_version > 0 && (
          <button type="button" onClick={toggleCode} className="self-start text-xs font-medium text-indigo-700 hover:underline">
            {showCode ? "Hide generated code" : "View generated code"}
          </button>
        )}
        {showCode && code && <pre className="max-h-64 overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-xs text-slate-100">{code}</pre>}
        {error && <p className="text-sm text-red-700">{error}</p>}
      </div>
    </article>
  );
}
