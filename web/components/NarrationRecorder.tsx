"use client";

import { useEffect, useRef, useState } from "react";

import { cutUrl, uploadTake } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { clock } from "@/lib/time";
import type { Hold, Project } from "@/lib/types";

import { Icon } from "./Icon";

type Phase = "loading" | "ready" | "recording" | "recorded" | "uploading";
type Paused = "no" | "paused" | "ended";
// Wall-clock time the animation fell behind (e.g. a decoding hiccup) that is worth keeping as a pause.
const DRIFT_S = 0.15;
const MIN_HOLD_S = 0.05;

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

/** `play()` rejects when a pause interrupts it; that is expected here, not an error. */
const play = (media: HTMLMediaElement | null) => media?.play().catch(() => undefined);

export function NarrationRecorder({ project, fromScene, onDone, onClose }: {
  project: Project;
  fromScene: string;
  onDone: (p: Project) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const holdsRef = useRef<Hold[]>([]);
  const startedAt = useRef(0); // performance.now() when the take started
  const pausedAt = useRef<{ video: number; wall: number } | null>(null);
  // The source of truth for pause state while recording; `paused` mirrors it for rendering.
  const pausedRef = useRef<Paused>("no");
  const discardRef = useRef(false);
  // Between pressing Start and the microphone being ready: a second start is ignored, a Space press is queued.
  const startingRef = useRef(false);
  const queuedToggle = useRef(false);
  const reviewFrame = useRef(0);
  const panelRef = useRef<HTMLDivElement>(null);

  // The video is fixed for the whole session: a background update must not swap it under a take.
  const [preview] = useState(() => project.preview);
  const [src, setSrc] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [paused, setPausedState] = useState<Paused>("no");
  const [now, setNow] = useState(0);
  const [pauseWall, setPauseWall] = useState<number | null>(null);
  const [videoTime, setVideoTime] = useState(0);
  const [take, setTake] = useState<{ blob: Blob; url: string; holds: Hold[] } | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const segments = preview.segments;
  const startIndex = Math.max(0, segments.findIndex((s) => s.scene_id === fromScene));
  const start = segments[startIndex]?.start ?? 0;
  const current = segments.findIndex((s) => videoTime >= s.start && videoTime < s.end);
  const shownIndex = current === -1 ? (videoTime >= preview.duration ? segments.length - 1 : startIndex) : current;
  const sceneOf = (i: number) => project.scenes.find((s) => s.id === segments[i]?.scene_id);

  const setPaused = (p: Paused) => {
    pausedRef.current = p;
    setPausedState(p);
  };

  // Load the whole animation up front so playback never stalls while recording.
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    fetch(cutUrl(project.id, "preview", preview))
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error("load"))))
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
        setPhase("ready");
      })
      .catch(() => !cancelled && setError(t.couldNotLoadVideo));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
    // Loaded once per session; the language of the error message does not matter for reloading.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, preview.version]);

  // Move focus into the dialog so keyboard and screen-reader users land in it, and return it on close.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => opener?.focus();
  }, []);

  const releaseMic = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const stopReview = () => {
    cancelAnimationFrame(reviewFrame.current);
    audioRef.current?.pause();
    videoRef.current?.pause();
    setReviewing(false);
  };

  useEffect(
    () => () => {
      discardRef.current = true;
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
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

  const seek = (time: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = time;
    setVideoTime(time);
  };

  /** Keep the take's wall clock and the animation in step: any time the animation lost becomes a pause. */
  const absorbDrift = (videoNow: number, wall: number) => {
    const held = holdsRef.current.reduce((a, h) => a + h.duration, 0);
    const drift = (wall - startedAt.current) / 1000 - (videoNow - start) - held;
    if (drift > DRIFT_S) holdsRef.current.push({ at: videoNow, duration: drift });
  };

  const closeHold = (wall: number) => {
    if (!pausedAt.current) return;
    holdsRef.current.push({ at: pausedAt.current.video, duration: (wall - pausedAt.current.wall) / 1000 });
    pausedAt.current = null;
  };

  async function startRecording() {
    if (startingRef.current || isRecording()) return;
    startingRef.current = true;
    queuedToggle.current = false;
    try {
      await beginTake();
    } finally {
      startingRef.current = false;
    }
    if (queuedToggle.current && isRecording()) togglePause();
  }

  // A function, not an inline check, so TypeScript does not assume the state is unchanged across `await`.
  function isRecording() {
    return recorderRef.current?.state === "recording";
  }

  async function beginTake() {
    setError(null);
    stopReview(); // a playback still running would drive the video (and be picked up by the microphone)
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError(t.micUnsupported);
      return;
    }
    try {
      streamRef.current ??= await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError(t.micDenied);
      return;
    }
    let recorder: MediaRecorder;
    try {
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      recorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : undefined);
    } catch {
      releaseMic();
      setError(t.micUnsupported);
      return;
    }
    const hadTake = take !== null;
    const chunks: Blob[] = [];
    holdsRef.current = [];
    pausedAt.current = null;
    discardRef.current = false;
    seek(start);
    recorder.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
    recorder.onstop = () => {
      releaseMic();
      videoRef.current?.pause();
      setPaused("no");
      if (discardRef.current) return;
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      if (blob.size === 0) {
        setError(t.emptyTake);
        setPhase(hadTake ? "recorded" : "ready");
        return;
      }
      setTake({ blob, url: URL.createObjectURL(blob), holds: holdsRef.current.filter((h) => h.duration > MIN_HOLD_S) });
      setPhase("recorded");
    };
    recorder.onerror = () => {
      discardRef.current = true;
      if (recorder.state !== "inactive") recorder.stop();
      releaseMic();
      videoRef.current?.pause();
      setPaused("no");
      setError(t.recorderFailed);
      setPhase(hadTake ? "recorded" : "ready");
    };
    recorderRef.current = recorder;
    try {
      recorder.start();
    } catch {
      releaseMic();
      setError(t.micUnsupported);
      return;
    }
    // The clock starts with the animation, so a pause pressed right away is measured correctly.
    startedAt.current = performance.now();
    setPaused("no");
    setPhase("recording");
    void play(videoRef.current);
  }

  function togglePause() {
    const v = videoRef.current;
    if (!v || recorderRef.current?.state !== "recording" || pausedRef.current === "ended") return;
    const wall = performance.now();
    if (pausedRef.current === "no") {
      absorbDrift(v.currentTime, wall);
      pausedAt.current = { video: v.currentTime, wall };
      v.pause();
      setPauseWall(wall);
      setPaused("paused");
    } else {
      closeHold(wall);
      void play(v);
      setPaused("no");
    }
  }

  function onEnded() {
    if (recorderRef.current?.state !== "recording") return;
    const wall = performance.now();
    const end = videoRef.current?.duration ?? preview.duration;
    if (pausedRef.current === "paused") closeHold(wall);
    absorbDrift(end, wall);
    pausedAt.current = { video: end, wall };
    setPauseWall(wall);
    setPaused("ended");
  }

  function stopRecording() {
    const recorder = recorderRef.current;
    const wall = performance.now();
    if (pausedAt.current) closeHold(wall);
    else if (videoRef.current) absorbDrift(videoRef.current.currentTime, wall);
    videoRef.current?.pause();
    if (recorder && recorder.state !== "inactive") recorder.stop();
    else setPhase(take ? "recorded" : "ready"); // the recorder already ended on its own
  }

  /** Close the dialog. A take in progress is discarded after confirming; an upload keeps going. */
  function requestClose() {
    if (recorderRef.current?.state === "recording") {
      if (!window.confirm(t.discardTake)) return;
      discardRef.current = true;
      recorderRef.current.stop();
    }
    stopReview();
    onClose();
  }

  // Keyboard: Space pauses/resumes the animation during a take (once per press), Escape closes.
  const handlers = useRef({ togglePause, requestClose });
  useEffect(() => {
    handlers.current = { togglePause, requestClose };
  });
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        handlers.current.requestClose();
        return;
      }
      if (e.code !== "Space") return;
      if (startingRef.current) {
        e.preventDefault(); // the microphone is still starting: apply this press once the take begins
        if (!e.repeat) queuedToggle.current = !queuedToggle.current;
        return;
      }
      if (recorderRef.current?.state !== "recording") return;
      // Also stops a focused button from "clicking" on Space and toggling a second time.
      e.preventDefault();
      if (!e.repeat) handlers.current.togglePause();
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space" && (startingRef.current || recorderRef.current?.state === "recording")) e.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  /** Play the take back with the animation pausing exactly where it will in the final video. */
  function playTake() {
    const a = audioRef.current;
    const v = videoRef.current;
    if (!a || !v || !take) return;
    if (reviewing) {
      stopReview();
      return;
    }
    cancelAnimationFrame(reviewFrame.current);
    a.currentTime = 0;
    seek(start);
    setReviewing(true);
    void play(a);
    const sync = () => {
      const { v: target, held } = videoTimeAt(a.currentTime, start, take.holds);
      const time = Math.min(target, v.duration || target);
      if (held || a.paused) {
        if (!v.paused) v.pause();
        if (Math.abs(v.currentTime - time) > 0.05) v.currentTime = time;
      } else {
        if (Math.abs(v.currentTime - time) > 0.3) v.currentTime = time;
        if (v.paused && time < (v.duration || Infinity)) void play(v);
      }
      if (!a.paused && !a.ended) reviewFrame.current = requestAnimationFrame(sync);
      else stopReview();
    };
    reviewFrame.current = requestAnimationFrame(sync);
  }

  async function useTake() {
    if (!take) return;
    stopReview();
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
  const pauseSeconds = pauseWall !== null ? Math.max(0, Math.floor((now - pauseWall) / 1000)) : 0;
  const pausesInTake = take?.holds.length ?? 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="recorder-heading"
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto overscroll-contain bg-stage/80 p-3 backdrop-blur-sm sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && requestClose()}
    >
      <div ref={panelRef} tabIndex={-1} className="stage outline-none max-h-full w-full max-w-5xl overflow-y-auto overscroll-contain rounded-2xl shadow-2xl ring-1 ring-white/10">
        {/* Pinned: the controls are the first thing seen and stay reachable however far the script scrolls. */}
        <div className="sticky top-0 z-10 space-y-3 border-b border-white/10 bg-stage/95 px-5 py-4 backdrop-blur sm:px-6">
          <div className="flex items-center justify-between gap-4">
            <h2 id="recorder-heading" className="font-serif text-xl font-semibold sm:text-2xl">
              {t.recordHeading}
              {start > 0 && <span className="font-sans text-base font-normal text-stage-muted"> {t.fromTime(clock(start))}</span>}
            </h2>
            <button
              type="button"
              onClick={requestClose}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-stage-muted hover:bg-white/10 hover:text-white"
              aria-label={t.close}
            >
              <Icon name="close" />
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {phase === "recording" ? (
              <>
                <button type="button" onClick={stopRecording} className="btn btn-record">
                  <span className="h-3 w-3 rounded-sm bg-white" aria-hidden="true" />
                  {t.stop}
                </button>
                <button
                  type="button"
                  onClick={togglePause}
                  disabled={paused === "ended"}
                  className="btn border border-gold/60 text-gold hover:bg-gold hover:text-stage"
                >
                  <Icon name={paused === "no" ? "pause" : "play"} size={16} />
                  {paused === "no" ? t.pauseAnimation : t.resumeAnimation}
                </button>
              </>
            ) : (
              <button type="button" onClick={startRecording} disabled={phase === "loading" || phase === "uploading"} className="btn btn-record">
                <Icon name="mic" size={16} />
                {take ? t.recordAgain : t.startRecording}
              </button>
            )}
            {take && phase !== "recording" && (
              <button
                type="button"
                onClick={playTake}
                disabled={phase !== "recorded"}
                className="btn border border-white/25 text-stage-ink hover:border-white/60"
              >
                <Icon name={reviewing ? "pause" : "play"} size={14} />
                {reviewing ? t.stopPlayback : t.playBack}
              </button>
            )}
            <span className="min-w-48 flex-1 text-sm text-stage-muted">
              {phase === "recording"
                ? t.spaceHint("Space")
                : phase === "recorded" || phase === "uploading"
                  ? t.pausesInTake(pausesInTake)
                  : t.recorderIdle}
            </span>
            {take && phase !== "recording" && (
              <button type="button" onClick={useTake} disabled={phase !== "recorded"} className="btn btn-primary">
                <Icon name="check" size={16} />
                {phase === "uploading" ? t.saving : t.useRecording}
              </button>
            )}
          </div>
          {error && src && (
            <p className="notice notice-error" role="alert">
              {error}
            </p>
          )}
        </div>

        <div className="space-y-4 p-5 sm:p-6">
          <div className="stage-grid relative overflow-hidden rounded-xl bg-black ring-1 ring-white/10">
            {src ? (
              <video
                ref={videoRef}
                src={src}
                muted
                playsInline
                onTimeUpdate={(e) => setVideoTime(e.currentTarget.currentTime)}
                onEnded={onEnded}
                className="mx-auto aspect-video max-h-[40vh] w-full object-contain"
              />
            ) : (
              <div className="grid aspect-video max-h-[40vh] w-full place-items-center px-6 text-center text-sm text-stage-muted">
                {error ?? t.loadingVideo}
              </div>
            )}
            <div
              aria-live="polite"
              className={
                "absolute top-3 left-3 flex max-w-[calc(100%-1.5rem)] items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold " +
                (phase !== "recording" ? "invisible" : paused !== "no" ? "bg-gold text-stage" : "bg-rec text-white")
              }
            >
              {phase === "recording" &&
                (paused === "no" ? (
                  <>
                    <span className="pulse-soft h-2 w-2 rounded-full bg-white" aria-hidden="true" />
                    {t.recordingBadge}
                  </>
                ) : (
                  <span className="tabular-nums">
                    {paused === "ended" ? t.endedKeepTalking(pauseSeconds) : t.pausedKeepTalking(pauseSeconds)}
                  </span>
                ))}
            </div>
            <div className="absolute right-3 bottom-3 rounded bg-black/65 px-2 py-0.5 text-xs font-medium text-white tabular-nums">
              {clock(videoTime)} / {clock(preview.duration)}
            </div>
          </div>

          <div className="rounded-xl bg-stage-raised px-5 py-4 sm:px-7">
            <p className="mb-2 text-sm text-stage-muted">{t.ownWords}</p>
            <p className="font-serif text-xl leading-relaxed text-stage-ink sm:text-2xl">{scene?.narration}</p>
            {next && (
              <p className="mt-4 border-t border-white/10 pt-3 text-sm leading-relaxed text-stage-muted">
                <span className="font-semibold">{t.next}</span> {next.narration}
              </p>
            )}
          </div>

          {take && <audio ref={audioRef} src={take.url} className="hidden" onEnded={stopReview} />}
        </div>
      </div>
    </div>
  );
}
