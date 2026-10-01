"use client";

import { useState } from "react";

import { audioUrl, clearVoice, generateAiVoice, generateAllAiVoice, getProject, updateNarration, videoUrl } from "@/lib/api";
import type { Project, Scene } from "@/lib/types";

import { ExportPanel } from "./ExportPanel";
import { ScenePreview } from "./ScenePreview";
import { SceneRecorder } from "./SceneRecorder";

function sourceBadge(scene: Scene): { label: string; className: string } {
  if (scene.audio_status === "generating") return { label: "Generating voice…", className: "bg-indigo-50 text-indigo-700 animate-pulse" };
  if (scene.audio_status === "failed") return { label: "Voice failed", className: "bg-red-50 text-red-700" };
  if (scene.audio_status === "done" && scene.audio_source === "ai") return { label: "AI voice", className: "bg-violet-50 text-violet-700" };
  if (scene.audio_status === "done" && scene.audio_source === "professor") return { label: "Your voice", className: "bg-emerald-50 text-emerald-700" };
  return { label: "No voice yet", className: "bg-slate-100 text-slate-600" };
}

export function VoiceStudio({ project, onChange }: { project: Project; onChange: (p: Project) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [recording, setRecording] = useState<Scene | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bust, setBust] = useState(0);

  async function act(key: string, fn: () => Promise<Project>) {
    setBusy(key);
    setError(null);
    try {
      onChange(await fn());
      setBust((b) => b + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      // Partial work (e.g. some scenes voiced before a failure) must show up; keep the UI in sync with the server.
      await getProject(project.id).then(onChange).catch(() => undefined);
    } finally {
      setBusy(null);
    }
  }

  const remaining = project.scenes.filter((s) => s.audio_status !== "done").length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-slate-600">Give each scene a voice: an AI voice, or your own recording. You can mix both.</p>
        <button
          type="button"
          onClick={() => act("all", () => generateAllAiVoice(project.id))}
          disabled={!!busy || remaining === 0}
          className="rounded-lg border border-violet-300 bg-violet-50 px-4 py-2 font-medium text-violet-800 hover:bg-violet-100 disabled:opacity-40"
        >
          {busy === "all" ? "Generating voices…" : `AI voice for all remaining (${remaining})`}
        </button>
      </div>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <ol className="space-y-3">
        {project.scenes.map((scene, i) => {
          const badge = sourceBadge(scene);
          return (
            <li key={scene.id} className="grid gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-[240px_1fr]">
              <div className="aspect-video overflow-hidden rounded-lg bg-black">
                <ScenePreview src={videoUrl(project.id, scene.id, scene.code_version)} muted className="h-full w-full" />
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold">
                    <span className="mr-1 text-slate-400">{i + 1}.</span>
                    {scene.title}
                  </h3>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>{badge.label}</span>
                </div>
                <textarea
                  key={`${scene.id}-${scene.narration}`}
                  defaultValue={scene.narration}
                  rows={2}
                  aria-label={`Narration for scene ${i + 1}`}
                  onBlur={(e) => {
                    const text = e.target.value.trim();
                    if (text && text !== scene.narration) act(scene.id, () => updateNarration(project.id, scene.id, text));
                  }}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => act(scene.id, () => generateAiVoice(project.id, scene.id))} disabled={!!busy} className="rounded-lg border border-violet-300 px-3 py-1.5 text-sm font-medium text-violet-800 hover:bg-violet-50 disabled:opacity-40">
                    {busy === scene.id ? "Working…" : "AI voice"}
                  </button>
                  <button type="button" onClick={() => setRecording(scene)} disabled={!!busy} className="rounded-lg border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-40">
                    ● Record my voice
                  </button>
                  {scene.audio_status === "done" && (
                    <>
                      <audio key={`${scene.id}-${bust}`} controls src={audioUrl(project.id, scene.id, bust)} className="h-9" />
                      <button type="button" onClick={() => act(scene.id, () => clearVoice(project.id, scene.id))} disabled={!!busy} className="text-sm text-slate-500 hover:text-red-600">
                        Remove
                      </button>
                    </>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <ExportPanel project={project} />

      {recording && (
        <SceneRecorder
          project={project}
          scene={recording}
          onClose={() => setRecording(null)}
          onDone={(p) => {
            onChange(p);
            setBust((b) => b + 1);
            setRecording(null);
          }}
        />
      )}
    </div>
  );
}
