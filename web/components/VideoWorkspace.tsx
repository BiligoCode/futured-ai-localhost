"use client";

import { useRef, useState } from "react";

import { composeVideo, cutUrl, generateAiNarration, removeNarration, startRender } from "@/lib/api";
import { clock, rangeOf } from "@/lib/time";
import type { Cut, CutKind, Project, Scene } from "@/lib/types";

import { ChangeRequest } from "./ChangeRequest";
import { NarrationRecorder } from "./NarrationRecorder";

const BUSY = new Set(["generating", "rendering", "repairing"]);

function phaseLabel(scenes: Scene[]): string {
  if (scenes.some((s) => s.render_status === "repairing" && s.last_error?.startsWith("Layout:"))) return "Checking the layout and tidying it up…";
  if (scenes.some((s) => s.render_status === "repairing")) return "Fixing a problem in the animation…";
  if (scenes.some((s) => s.render_status === "rendering")) return "Rendering the animation…";
  return "Writing the animation…";
}

/** A slim bar under the player that highlights the parts of the video being changed. */
function Timeline({ cut, busy }: { cut: Cut; busy: Set<string> }) {
  if (!cut.duration) return null;
  return (
    <div className="relative h-1.5 overflow-hidden rounded-full bg-slate-200" aria-hidden>
      {cut.segments
        .filter((s) => busy.has(s.scene_id))
        .map((s) => (
          <div
            key={s.scene_id}
            className="absolute inset-y-0 animate-pulse bg-amber-400"
            style={{ left: `${(s.start / cut.duration) * 100}%`, width: `${((s.end - s.start) / cut.duration) * 100}%` }}
          />
        ))}
    </div>
  );
}

function Notice({ tone, children }: { tone: "info" | "warn" | "error"; children: React.ReactNode }) {
  const styles = { info: "bg-indigo-50 text-indigo-800", warn: "bg-amber-50 text-amber-900", error: "bg-red-50 text-red-800" };
  return <div className={`rounded-lg p-3 text-sm ${styles[tone]}`}>{children}</div>;
}

/** The video player. Manim animations open on an empty frame, so show a frame from inside the video until played. */
function Player({ src, onPausedAt }: { src: string; onPausedAt: (t: number | null) => void }) {
  const started = useRef(false);
  return (
    <video
      src={src}
      controls
      preload="metadata"
      className="aspect-video w-full"
      onLoadedMetadata={(e) => {
        const v = e.currentTarget;
        if (!started.current && Number.isFinite(v.duration)) v.currentTime = Math.min(v.duration * 0.3, 8);
      }}
      onPlay={(e) => {
        if (!started.current) {
          started.current = true;
          e.currentTarget.currentTime = 0;
        }
        onPausedAt(null);
      }}
      onPause={(e) => {
        const v = e.currentTarget;
        onPausedAt(started.current && v.currentTime > 0 && !v.ended ? v.currentTime : null);
      }}
    />
  );
}

export function VideoWorkspace({ project, onChange }: { project: Project; onChange: (p: Project) => void }) {
  const [recordFrom, setRecordFrom] = useState<string | null>(null);
  const [playerAt, setPlayerAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);

  async function act(fn: () => Promise<Project>) {
    setActing(true);
    setError(null);
    try {
      onChange(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActing(false);
    }
  }

  const { scenes, preview, final } = project;
  const busyScenes = scenes.filter((s) => BUSY.has(s.render_status));
  const failedScenes = scenes.filter((s) => s.render_status === "failed");

  // First build: nothing to watch yet, just progress.
  if (preview.version === 0) {
    const ready = scenes.filter((s) => s.render_status === "done").length;
    const stuck = failedScenes.length > 0 && busyScenes.length === 0;
    return (
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto grid aspect-video max-w-3xl place-items-center rounded-lg bg-slate-900 text-slate-300">
          <div className="space-y-4 px-6">
            <p className="text-lg font-medium text-white">
              {stuck ? "Part of the video could not be created" : ready === scenes.length ? "Putting your video together…" : "Lara is creating your video"}
            </p>
            {!stuck && ready < scenes.length && <p className="text-sm">{phaseLabel(busyScenes)}</p>}
            <div className="mx-auto h-2 w-72 overflow-hidden rounded-full bg-slate-700">
              <div className="h-full bg-indigo-500 transition-all" style={{ width: `${Math.max(5, (ready / scenes.length) * 100)}%` }} />
            </div>
          </div>
        </div>
        {stuck && (
          <button type="button" onClick={() => act(() => startRender(project.id))} disabled={acting} className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-40">
            Try again
          </button>
        )}
        {preview.status === "failed" && (
          <Notice tone="error">
            The video could not be put together: {preview.error}{" "}
            <button type="button" onClick={() => act(() => composeVideo(project.id))} className="font-medium underline">Try again</button>
          </Notice>
        )}
        {error && <Notice tone="error">{error}</Notice>}
      </section>
    );
  }

  const kind: CutKind = final.version > 0 ? "final" : "preview";
  const cut = project[kind];
  const busyIds = new Set(busyScenes.map((s) => s.id));
  const changing = busyScenes.map((s) => rangeOf(cut, s.id)).filter(Boolean);
  const updating = (["preview", "final"] as const).some((k) => project[k].status === "building" || (project[`${k}_outdated`] && project[k].status !== "failed"));
  const unapplied = scenes.filter((s) => s.render_status === "done" && s.last_error);
  const voiced = scenes.filter((s) => s.audio_status === "done");
  const sources = new Set(voiced.map((s) => s.audio_source));
  const stale = scenes.filter((s) => s.audio_stale && s.audio_status === "done");
  const voiceFailed = scenes.some((s) => s.audio_status === "failed");
  const cutFailed = (["preview", "final"] as const).find((k) => project[k].status === "failed");
  const firstStart = preview.segments[0]?.scene_id ?? scenes[0].id;

  const narrationLabel =
    voiced.length === 0
      ? "No narration yet"
      : sources.size > 1
        ? "Narrated with your voice and the AI voice"
        : sources.has("professor")
          ? voiced.length === scenes.length
            ? "Narrated with your voice"
            : "Your voice covers part of the video; the rest is silent"
          : "Narrated with the AI voice";

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-3">
        <div className="overflow-hidden rounded-xl bg-black shadow-sm">
          <Player key={`${kind}-${cut.version}`} src={cutUrl(project.id, kind, cut.version)} onPausedAt={setPlayerAt} />
        </div>
        <Timeline cut={cut} busy={busyIds} />
        <div className="space-y-2">
          {changing.length > 0 && (
            <Notice tone="info">
              Changing {changing.join(", ")}… {phaseLabel(busyScenes)} The video updates when it&apos;s ready.
            </Notice>
          )}
          {changing.length === 0 && updating && <Notice tone="info">Updating the video…</Notice>}
          {unapplied.map((s) => (
            <Notice key={s.id} tone="warn">
              The change at {rangeOf(cut, s.id) ?? "one part"} could not be applied; the previous version is kept. Try describing it differently.
            </Notice>
          ))}
          {failedScenes.length > 0 && busyScenes.length === 0 && (
            <Notice tone="error">
              Part of the video could not be rebuilt.{" "}
              <button type="button" onClick={() => act(() => startRender(project.id))} className="font-medium underline">Try again</button>
            </Notice>
          )}
          {cutFailed && (
            <Notice tone="error">
              The video could not be put together: {project[cutFailed].error}{" "}
              <button type="button" onClick={() => act(() => composeVideo(project.id))} className="font-medium underline">Try again</button>
            </Notice>
          )}
          {error && <Notice tone="error">{error}</Notice>}
        </div>
        <ChangeRequest
          project={project}
          cut={kind}
          playerAt={playerAt}
          onClearPlayerAt={() => setPlayerAt(null)}
          onChange={onChange}
        />
      </div>

      <aside className="space-y-4">
        <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div>
            <h2 className="font-semibold">Narration</h2>
            <p className="text-sm text-slate-600">{project.narrating ? "Generating the AI voice…" : narrationLabel}</p>
          </div>

          {stale.map((s) => (
            <Notice key={s.id} tone="warn">
              {rangeOf(preview, s.id)} changed after you recorded it.{" "}
              <button type="button" onClick={() => setRecordFrom(s.id)} className="font-medium underline">
                Re-record from {clock(preview.segments.find((g) => g.scene_id === s.id)?.start ?? 0)}
              </button>
            </Notice>
          ))}
          {voiceFailed && !project.narrating && <Notice tone="error">The AI voice failed for part of the video. Try again below.</Notice>}

          <button
            type="button"
            onClick={() => setRecordFrom(firstStart)}
            disabled={acting || project.narrating || busyScenes.length > 0 || preview.status !== "done" || project.preview_outdated}
            className="w-full rounded-lg bg-red-600 px-4 py-3 text-left font-medium text-white hover:bg-red-700 disabled:opacity-40"
          >
            🎙 {sources.has("professor") ? "Record again" : "Record your voice"}
            <span className="block text-xs font-normal text-red-100">The animation plays while you talk. Pause it anytime to explain longer; the pause stays in the video.</span>
          </button>
          <button
            type="button"
            onClick={() => {
              if (sources.has("professor") && !confirm("Replace your recording with the AI voice?")) return;
              void act(() => generateAiNarration(project.id));
            }}
            disabled={acting || project.narrating || (voiced.length === scenes.length && !sources.has("professor") && !voiceFailed)}
            className="w-full rounded-lg border border-violet-300 bg-violet-50 px-4 py-3 text-left font-medium text-violet-900 hover:bg-violet-100 disabled:opacity-40"
          >
            ✨ {project.narrating ? "Generating…" : "Use the AI voice"}
            <span className="block text-xs font-normal text-violet-700">Reads the script in a natural voice.</span>
          </button>
          {voiced.length > 0 && (
            <button
              type="button"
              onClick={() => confirm("Remove all narration?") && act(() => removeNarration(project.id))}
              disabled={acting || project.narrating}
              className="text-sm text-slate-500 hover:text-red-600 disabled:opacity-40"
            >
              Remove narration
            </button>
          )}
        </section>

        <section className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-5">
          <h2 className="font-semibold">Download</h2>
          <p className="text-sm text-slate-600">
            {cut.duration ? `${clock(cut.duration)} · ` : ""}
            {kind === "final" ? "With narration." : "Animation only, no narration yet."}
          </p>
          <a
            href={cutUrl(project.id, kind, cut.version)}
            download
            aria-disabled={updating}
            className={"inline-block rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 " + (updating ? "pointer-events-none opacity-40" : "")}
          >
            ⬇ Download MP4
          </a>
        </section>
      </aside>

      {recordFrom && (
        <NarrationRecorder
          project={project}
          fromScene={recordFrom}
          onClose={() => setRecordFrom(null)}
          onDone={(p) => {
            onChange(p);
            setRecordFrom(null);
          }}
        />
      )}
    </div>
  );
}
