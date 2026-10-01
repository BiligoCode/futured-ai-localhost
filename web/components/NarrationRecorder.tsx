"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { cutUrl, uploadTake } from "@/lib/api";
import { clock } from "@/lib/time";
import type { Hold, Project } from "@/lib/types";

type Phase = "loading" | "ready" | "recording" | "recorded" | "uploading";
// Wall-clock time the animation fell behind (e.g. a decoding hiccup) that is worth keeping as a pause.
const DRIFT_S = 0.15;

/** Where the animation is (`v`) and whether it is held, `r` seconds into a take that started at `start`. */
function videoTimeAt(r: number, start: number, holds: Hold[]): { v: number; held: boolean } {
  let shift = 0;
  for (const h of holds) {
    const holdStart = h.at - start + shift;
    if (r < holdStart) break;
    if (r < holdStart + h.duration) return { v: h.at, held: true };
    shift += h.duration;
  }
  return { v: start + r - shift, held: false };
}

export function NarrationRecorder({ project, fromScene, onDone, onClose }: {
  project: Project;
  fromScene: string;
  onDone: (p: Project) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const holdsRef = useRef<Hold[]>([]);
  const startedAt = useRef(0); // performance.now() when the take started
  const pausedAt = useRef<{ video: number; wall: number } | null>(null);
  const reviewFrame = useRef(0);

  const [src, setSrc] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [paused, setPaused] = useState<"no" | "paused" | "ended">("no");
  const [now, setNow] = useState(0);
  const [pauseWall, setPauseWall] = useState<number | null>(null);
  const [videoTime, setVideoTime] = useState(0);
  const [take, setTake] = useState<{ blob: Blob; url: string; holds: Hold[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const segments = project.preview.segments;
  const startIndex = Math.max(0, segments.findIndex((s) => s.scene_id === fromScene));
  const start = segments[startIndex]?.start ?? 0;
  const current = segments.findIndex((s) => videoTime >= s.start && videoTime < s.end);
  const shownIndex = current === -1 ? (videoTime >= project.preview.duration ? segments.length - 1 : startIndex) : current;
  const sceneOf = (i: number) => project.scenes.find((s) => s.id === segments[i]?.scene_id);

  // Load the whole animation up front so playback never stalls while recording.
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    fetch(cutUrl(project.id, "preview", project.preview.version))
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error("Could not load the video"))))
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
        setPhase("ready");
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [project.id, project.preview.version]);

  useEffect(
    () => () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      cancelAnimationFrame(reviewFrame.current);
    },
    [],
  );
  useEffect(() => () => {
    if (take) URL.revokeObjectURL(take.url);
  }, [take]);

  // Tick a clock while recording (for the pause timer).
  useEffect(() => {
    if (phase !== "recording") return;
    const timer = setInterval(() => setNow(performance.now()), 200);
    return () => clearInterval(timer);
  }, [phase]);

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = t;
    setVideoTime(t);
  };

  /** Keep the take's wall clock and the animation in step: any time the animation lost becomes a pause. */
  const absorbDrift = (videoNow: number, wall: number) => {
    const held = holdsRef.current.reduce((a, h) => a + h.duration, 0);
    const drift = (wall - startedAt.current) / 1000 - (videoNow - start) - held;
    if (drift > DRIFT_S) holdsRef.current.push({ at: videoNow, duration: drift });
  };

  async function startRecording() {
    setError(null);
    try {
      streamRef.current ??= await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access was denied. Allow microphone access in your browser to record your voice.");
      return;
    }
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    const recorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    holdsRef.current = [];
    pausedAt.current = null;
    seek(start);
    recorder.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
    recorder.onstart = () => {
      startedAt.current = performance.now();
      void videoRef.current?.play();
    };
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      setTake({ blob, url: URL.createObjectURL(blob), holds: [...holdsRef.current] });
      setPhase("recorded");
    };
    recorderRef.current = recorder;
    setPaused("no");
    setPhase("recording");
    recorder.start();
  }

  const togglePause = useCallback(() => {
    const v = videoRef.current;
    if (!v || phase !== "recording" || paused === "ended") return;
    const wall = performance.now();
    if (paused === "no") {
      absorbDrift(v.currentTime, wall);
      pausedAt.current = { video: v.currentTime, wall };
      v.pause();
      setPauseWall(wall);
      setPaused("paused");
    } else if (pausedAt.current) {
      holdsRef.current.push({ at: pausedAt.current.video, duration: (wall - pausedAt.current.wall) / 1000 });
      pausedAt.current = null;
      void v.play();
      setPaused("no");
    }
    // absorbDrift reads only refs and `start`, which is fixed for the dialog's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, paused]);

  function onEnded() {
    if (phase !== "recording") return;
    const wall = performance.now();
    const end = videoRef.current?.duration ?? project.preview.duration;
    absorbDrift(end, wall);
    pausedAt.current = { video: end, wall };
    setPauseWall(wall);
    setPaused("ended");
  }

  function stopRecording() {
    const v = videoRef.current;
    const wall = performance.now();
    if (pausedAt.current) {
      holdsRef.current.push({ at: pausedAt.current.video, duration: (wall - pausedAt.current.wall) / 1000 });
      pausedAt.current = null;
    } else if (v) {
      absorbDrift(v.currentTime, wall);
    }
    holdsRef.current = holdsRef.current.filter((h) => h.duration > 0.05);
    v?.pause();
    setPaused("no");
    recorderRef.current?.stop();
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space" && phase === "recording") {
        e.preventDefault();
        togglePause();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, togglePause]);

  /** Play the take back with the animation pausing exactly where it will in the final video. */
  function playTake() {
    const a = audioRef.current;
    const v = videoRef.current;
    if (!a || !v || !take) return;
    cancelAnimationFrame(reviewFrame.current);
    a.currentTime = 0;
    seek(start);
    void a.play();
    const sync = () => {
      const { v: target, held } = videoTimeAt(a.currentTime, start, take.holds);
      const t = Math.min(target, v.duration || target);
      if (held || a.paused) {
        if (!v.paused) v.pause();
        if (Math.abs(v.currentTime - t) > 0.05) v.currentTime = t;
      } else {
        if (Math.abs(v.currentTime - t) > 0.3) v.currentTime = t;
        if (v.paused && t < (v.duration || Infinity)) void v.play();
      }
      if (!a.paused && !a.ended) reviewFrame.current = requestAnimationFrame(sync);
      else v.pause();
    };
    reviewFrame.current = requestAnimationFrame(sync);
  }

  async function useTake() {
    if (!take) return;
    cancelAnimationFrame(reviewFrame.current);
    audioRef.current?.pause();
    setPhase("uploading");
    setError(null);
    try {
      onDone(await uploadTake(project.id, take.blob, fromScene, take.holds));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("recorded");
    }
  }

  const scene = sceneOf(shownIndex);
  const next = sceneOf(shownIndex + 1);
  const pauseSeconds = pauseWall !== null ? Math.max(0, (now - pauseWall) / 1000) : 0;
  const btn = "rounded-lg px-4 py-2 font-medium disabled:opacity-40";

  return (
    <div role="dialog" aria-modal="true" aria-label="Record your narration" className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-900/70 p-4">
      <div className="max-h-full w-full max-w-5xl space-y-4 overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            Record your narration{start > 0 && <span className="font-normal text-slate-500"> · from {clock(start)}</span>}
          </h2>
          <button type="button" onClick={onClose} disabled={phase === "recording" || phase === "uploading"} className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30" aria-label="Close">✕</button>
        </div>

        <div className={"rounded-lg px-4 py-1.5 text-center text-sm font-medium " + (phase === "recording" ? (paused !== "no" ? "bg-amber-100 text-amber-900" : "bg-red-50 text-red-700") : "invisible")}>
          {paused === "no"
            ? "● Recording — the animation is playing"
            : `${paused === "ended" ? "Animation finished" : "Animation paused"} — keep talking · ${pauseSeconds.toFixed(0)}s`}
        </div>

        <div className="relative">
          {src ? (
            <video
              ref={videoRef}
              src={src}
              muted
              playsInline
              onTimeUpdate={(e) => setVideoTime(e.currentTarget.currentTime)}
              onEnded={onEnded}
              className="mx-auto aspect-video max-h-[46vh] w-full rounded-lg bg-black object-contain"
            />
          ) : (
            <div className="grid aspect-video max-h-[46vh] w-full place-items-center rounded-lg bg-black text-sm text-slate-400">Loading the video…</div>
          )}
          <div className="absolute bottom-3 right-3 rounded bg-black/60 px-2 py-0.5 font-mono text-xs text-white">
            {clock(videoTime)} / {clock(project.preview.duration)}
          </div>
        </div>

        <div className="rounded-xl bg-slate-900 p-5">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Script · say it in your own words</p>
          <p className="text-xl leading-relaxed text-white">{scene?.narration}</p>
          {next && <p className="mt-3 text-sm leading-relaxed text-slate-500">Next: {next.narration}</p>}
        </div>

        {take && <audio ref={audioRef} src={take.url} className="hidden" />}
        {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <div className="flex flex-wrap items-center gap-3">
          {phase === "recording" ? (
            <>
              <button type="button" onClick={stopRecording} className={`${btn} bg-red-600 text-white hover:bg-red-700`}>
                <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-white" />
                Stop
              </button>
              <button type="button" onClick={togglePause} disabled={paused === "ended"} className={`${btn} border border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100`}>
                {paused === "no" ? "❚❚ Pause animation" : "▶ Resume animation"}
              </button>
            </>
          ) : (
            <button type="button" onClick={startRecording} disabled={phase === "loading" || phase === "uploading"} className={`${btn} bg-red-600 text-white hover:bg-red-700`}>
              {take ? "Record again" : "● Start recording"}
            </button>
          )}
          {take && phase !== "recording" && (
            <button type="button" onClick={playTake} disabled={phase !== "recorded"} className={`${btn} border border-slate-300 hover:bg-slate-100`}>
              ▶ Play back
            </button>
          )}
          <span className="flex-1 text-sm text-slate-500">
            {phase === "recording"
              ? "Recording. Press Space to pause the animation while you explain; the pause stays in the video."
              : phase === "recorded"
                ? `${take?.holds.length ?? 0} pause${take?.holds.length === 1 ? "" : "s"} in this take.`
                : "The animation plays while you talk. You can pause it at any moment to explain longer."}
          </span>
          {take && phase !== "recording" && (
            <button type="button" onClick={useTake} disabled={phase !== "recorded"} className={`${btn} bg-indigo-600 text-white hover:bg-indigo-700`}>
              {phase === "uploading" ? "Saving…" : "Use this recording"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
