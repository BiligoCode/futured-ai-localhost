"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { cutUrl, uploadTake } from "@/lib/api";
import { clock } from "@/lib/time";
import type { Hold, Project } from "@/lib/types";

import { Icon } from "./Icon";

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
  const panelRef = useRef<HTMLDivElement>(null);

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

  // Move focus into the dialog so keyboard and screen-reader users land in it, and return it on close.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => opener?.focus();
  }, []);

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
      } else if (e.key === "Escape" && phase !== "recording" && phase !== "uploading") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, togglePause, onClose]);

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
  const closable = phase !== "recording" && phase !== "uploading";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="recorder-heading"
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto overscroll-contain bg-stage/80 p-3 backdrop-blur-sm sm:p-6"
    >
      <div ref={panelRef} tabIndex={-1} className="stage outline-none max-h-full w-full max-w-5xl space-y-5 overflow-y-auto overscroll-contain rounded-2xl p-5 shadow-2xl ring-1 ring-white/10 sm:p-6">
        <div className="flex items-center justify-between gap-4">
          <h2 id="recorder-heading" className="font-serif text-2xl font-semibold">
            Record your narration
            {start > 0 && <span className="font-sans text-base font-normal text-stage-muted"> from {clock(start)}</span>}
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={!closable}
            className="grid h-9 w-9 place-items-center rounded-md text-stage-muted hover:bg-white/10 hover:text-white disabled:opacity-30"
            aria-label="Close"
          >
            <Icon name="close" />
          </button>
        </div>

        <div className="stage-grid relative overflow-hidden rounded-xl bg-black ring-1 ring-white/10">
          {src ? (
            <video
              ref={videoRef}
              src={src}
              muted
              playsInline
              onTimeUpdate={(e) => setVideoTime(e.currentTarget.currentTime)}
              onEnded={onEnded}
              className="mx-auto aspect-video max-h-[44vh] w-full object-contain"
            />
          ) : (
            <div className="grid aspect-video max-h-[44vh] w-full place-items-center text-sm text-stage-muted">Loading the video…</div>
          )}
          <div
            aria-live="polite"
            className={
              "absolute top-3 left-3 flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold " +
              (phase !== "recording" ? "invisible" : paused !== "no" ? "bg-gold text-stage" : "bg-rec text-white")
            }
          >
            {phase === "recording" &&
              (paused === "no" ? (
                <>
                  <span className="pulse-soft h-2 w-2 rounded-full bg-white" aria-hidden="true" />
                  Recording
                </>
              ) : (
                <span className="tabular-nums">
                  {paused === "ended" ? "Animation finished" : "Animation paused"}, keep talking · {pauseSeconds.toFixed(0)}s
                </span>
              ))}
          </div>
          <div className="absolute right-3 bottom-3 rounded bg-black/65 px-2 py-0.5 text-xs font-medium text-white tabular-nums">
            {clock(videoTime)} / {clock(project.preview.duration)}
          </div>
        </div>

        <div className="rounded-xl bg-stage-raised px-5 py-5 sm:px-7">
          <p className="mb-2 text-sm text-stage-muted">Say it in your own words</p>
          <p className="font-serif text-2xl leading-relaxed text-stage-ink sm:text-[1.75rem]">{scene?.narration}</p>
          {next && (
            <p className="mt-4 border-t border-white/10 pt-3 text-sm leading-relaxed text-stage-muted">
              <span className="font-semibold">Next:</span> {next.narration}
            </p>
          )}
        </div>

        {take && <audio ref={audioRef} src={take.url} className="hidden" />}
        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          {phase === "recording" ? (
            <>
              <button type="button" onClick={stopRecording} className="btn btn-record">
                <span className="h-3 w-3 rounded-sm bg-white" aria-hidden="true" />
                Stop
              </button>
              <button
                type="button"
                onClick={togglePause}
                disabled={paused === "ended"}
                className="btn border border-gold/60 text-gold hover:bg-gold hover:text-stage"
              >
                <Icon name={paused === "no" ? "pause" : "play"} size={16} />
                {paused === "no" ? "Pause animation" : "Resume animation"}
              </button>
            </>
          ) : (
            <button type="button" onClick={startRecording} disabled={phase === "loading" || phase === "uploading"} className="btn btn-record">
              <Icon name="mic" size={16} />
              {take ? "Record again" : "Start recording"}
            </button>
          )}
          {take && phase !== "recording" && (
            <button
              type="button"
              onClick={playTake}
              disabled={phase !== "recorded"}
              className="btn border border-white/25 text-stage-ink hover:border-white/60"
            >
              <Icon name="play" size={14} />
              Play back
            </button>
          )}
          <span className="min-w-48 flex-1 text-sm text-stage-muted">
            {phase === "recording" ? (
              <>
                Press <kbd className="rounded border border-white/25 px-1.5 py-0.5 font-sans text-xs text-stage-ink">Space</kbd> to pause the animation while you explain; the pause stays in the video.
              </>
            ) : phase === "recorded" ? (
              `${take?.holds.length ?? 0} pause${take?.holds.length === 1 ? "" : "s"} in this take.`
            ) : (
              "The animation plays while you talk. You can pause it at any moment to explain longer."
            )}
          </span>
          {take && phase !== "recording" && (
            <button type="button" onClick={useTake} disabled={phase !== "recorded"} className="btn btn-primary">
              <Icon name="check" size={16} />
              {phase === "uploading" ? "Saving…" : "Use this recording"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
