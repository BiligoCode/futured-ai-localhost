"use client";

import { useEffect, useRef, useState } from "react";

import { uploadRecording, videoUrl } from "@/lib/api";
import type { Project, Scene } from "@/lib/types";

type Phase = "idle" | "recording" | "recorded" | "uploading";

export function SceneRecorder({ project, scene, onDone, onClose }: {
  project: Project;
  scene: Scene;
  onDone: (p: Project) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [take, setTake] = useState<{ blob: Blob; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(
    () => () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    },
    [],
  );
  useEffect(() => () => {
    if (take) URL.revokeObjectURL(take.url);
  }, [take]);

  function playVideoFromStart() {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = 0;
    void v.play();
  }

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
    recorder.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      setTake({ blob, url: URL.createObjectURL(blob) });
      setPhase("recorded");
    };
    recorderRef.current = recorder;
    recorder.start();
    setPhase("recording");
    playVideoFromStart();
  }

  function stopRecording() {
    recorderRef.current?.stop();
    videoRef.current?.pause();
  }

  function playTake() {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = 0;
    playVideoFromStart();
    void a.play();
  }

  async function useTake() {
    if (!take) return;
    setPhase("uploading");
    setError(null);
    try {
      onDone(await uploadRecording(project.id, scene.id, take.blob));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("recorded");
    }
  }

  const btn = "rounded-lg px-4 py-2 font-medium disabled:opacity-40";
  return (
    <div role="dialog" aria-modal="true" aria-label={`Record narration for ${scene.title}`} className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-900/70 p-4">
      <div className="max-h-full w-full max-w-4xl space-y-4 overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Record your voice — {scene.title}</h2>
          <button type="button" onClick={onClose} className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="Close">✕</button>
        </div>

        <video ref={videoRef} src={videoUrl(project.id, scene.id, scene.code_version)} muted playsInline className="mx-auto aspect-video max-h-[42vh] w-full rounded-lg bg-black object-contain" />

        <div className="rounded-xl bg-slate-900 p-6">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Teleprompter</p>
          <p className="text-2xl leading-relaxed text-white">{scene.narration}</p>
        </div>

        {take && <audio ref={audioRef} src={take.url} className="hidden" />}
        {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <div className="flex flex-wrap items-center gap-3">
          {phase === "recording" ? (
            <button type="button" onClick={stopRecording} className={`${btn} bg-red-600 text-white hover:bg-red-700`}>
              <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-white" />
              Stop
            </button>
          ) : (
            <button type="button" onClick={startRecording} disabled={phase === "uploading"} className={`${btn} bg-red-600 text-white hover:bg-red-700`}>
              {take ? "Retake" : "● Record"}
            </button>
          )}
          <button type="button" onClick={playTake} disabled={!take || phase !== "recorded"} className={`${btn} border border-slate-300 hover:bg-slate-100`}>
            ▶ Play take
          </button>
          <span className="flex-1 text-sm text-slate-500">
            {phase === "recording" ? "Recording… read the text while the animation plays." : phase === "idle" ? "Press Record: the animation starts with your recording." : ""}
          </span>
          <button type="button" onClick={useTake} disabled={!take || phase !== "recorded"} className={`${btn} bg-indigo-600 text-white hover:bg-indigo-700`}>
            {phase === "uploading" ? "Saving…" : "Use this take"}
          </button>
        </div>
      </div>
    </div>
  );
}
