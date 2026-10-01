"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { cancelProject, composeVideo, cutUrl, generateAiNarration, removeNarration, setCaptions, startRender } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Messages } from "@/lib/messages";
import { clock, rangeOf } from "@/lib/time";
import type { Cut, CutKind, Project, Scene } from "@/lib/types";

import { ChangeRequest } from "./ChangeRequest";
import { EmbedDialog } from "./deck/EmbedDialog";
import { Icon } from "./Icon";
import { NarrationRecorder } from "./NarrationRecorder";
import { CurveSketch } from "./Stage";

const BUSY = new Set(["generating", "rendering", "repairing"]);
const CANCELLED = "Cancelled"; // the API's last_error for parts the professor stopped

function phaseLabel(scenes: Scene[], t: Messages): string {
  if (scenes.some((s) => s.render_status === "repairing" && s.last_error?.startsWith("Layout:"))) return t.phaseLayout;
  if (scenes.some((s) => s.render_status === "repairing")) return t.phaseFixing;
  if (scenes.some((s) => s.render_status === "rendering")) return t.phaseRendering;
  return t.phaseWriting;
}

/** A slim bar under the player: part boundaries as ticks, parts being changed in gold. */
function Timeline({ cut, busy }: { cut: Cut; busy: Set<string> }) {
  if (!cut.duration) return null;
  const pct = (t: number) => `${(t / cut.duration) * 100}%`;
  return (
    <div className="relative h-1.5 rounded-full bg-rule" aria-hidden="true">
      {cut.segments
        .filter((s) => busy.has(s.scene_id))
        .map((s) => (
          <div key={s.scene_id} className="pulse-soft absolute inset-y-0 rounded-full bg-gold" style={{ left: pct(s.start), width: pct(s.end - s.start) }} />
        ))}
      {cut.segments.slice(1).map((s) => (
        <div key={s.scene_id} className="absolute -inset-y-0.5 w-0.5 -translate-x-1/2 bg-paper" style={{ left: pct(s.start) }} />
      ))}
    </div>
  );
}

function Notice({ tone, children }: { tone: "info" | "warn" | "error"; children: React.ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "error" ? "alert" : undefined}>
      <p>{children}</p>
    </div>
  );
}

/** The video player. Manim animations open on an empty frame, so show a frame from inside the video until played. */
function Player({ src, onPausedAt }: { src: string; onPausedAt: (t: number | null) => void }) {
  const started = useRef(false);
  return (
    <video
      src={src}
      controls
      preload="metadata"
      playsInline
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

/** Captions for the AI voice: an explicit On/Off switch that says its state in words. */
function CaptionsSwitch({ on, disabled, hint, updating, onToggle }: {
  on: boolean;
  disabled: boolean;
  hint: string;
  updating: boolean;
  onToggle: (on: boolean) => void;
}) {
  const { t } = useI18n();
  return (
    <div className={`flex items-center gap-3 border-t border-rule bg-sunken/60 px-4 py-3 ${disabled ? "opacity-60" : ""}`}>
      <span className="min-w-0 flex-1">
        <span id="captions-label" className="block text-sm font-semibold">
          {t.captions}
        </span>
        <span className="block text-xs text-muted">{hint}</span>
        {updating && <span className="mt-1 block text-xs text-gold-ink">{t.captionsUpdating}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-labelledby="captions-label"
        disabled={disabled}
        onClick={() => onToggle(!on)}
        className="flex shrink-0 items-center gap-2 rounded-full text-sm font-semibold disabled:cursor-not-allowed"
      >
        <span className={`w-9 text-right ${on ? "text-accent" : "text-muted"}`}>{on ? t.captionsOn : t.captionsOff}</span>
        <span
          className={`relative h-6 w-11 rounded-full transition-colors ${on ? "bg-accent" : "bg-rule-strong"}`}
          aria-hidden="true"
        >
          <span
            className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform motion-reduce:transition-none ${on ? "translate-x-5" : ""}`}
          />
        </span>
      </button>
    </div>
  );
}

export function VideoWorkspace({ project, onChange }: { project: Project; onChange: (p: Project) => void }) {
  const { t } = useI18n();
  const [recordFrom, setRecordFrom] = useState<string | null>(null);
  const [embedding, setEmbedding] = useState(false);
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
    const stopped = stuck && failedScenes.every((s) => s.last_error === CANCELLED);
    return (
      <section className="space-y-4">
        <div className="stage stage-grid grid aspect-video max-h-[70vh] w-full place-items-center rounded-2xl">
          <div className="w-full max-w-md space-y-6 px-6 text-center" aria-live="polite">
            {!stuck && <CurveSketch className="mx-auto w-full max-w-xs" />}
            <div className="space-y-2">
              <p className="font-serif text-2xl leading-tight font-semibold sm:text-3xl">
                {stopped ? t.stopped : stuck ? t.partFailed : ready === scenes.length ? t.puttingTogether : t.creating}
              </p>
              {!stuck && ready < scenes.length && <p className="text-sm text-stage-muted">{phaseLabel(busyScenes, t)}</p>}
            </div>
            <div className="space-y-2">
              <div
                className="mx-auto h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-stage-raised"
                role="progressbar"
                aria-label={t.partsReadyLabel}
                aria-valuemin={0}
                aria-valuemax={scenes.length}
                aria-valuenow={ready}
              >
                <div
                  className="h-full rounded-full bg-manim transition-[width] duration-700 ease-out motion-reduce:transition-none"
                  style={{ width: `${Math.max(4, (ready / scenes.length) * 100)}%` }}
                />
              </div>
              <p className="text-xs text-stage-muted tabular-nums">
                {t.partsReady(ready, scenes.length)}
              </p>
            </div>
            {stuck && (
              <button type="button" onClick={() => act(() => startRender(project.id))} disabled={acting} className="btn btn-primary">
                {stopped ? t.resume : t.tryAgain}
              </button>
            )}
            {busyScenes.length > 0 && (
              <button type="button" onClick={() => act(() => cancelProject(project.id))} disabled={acting} className="btn btn-secondary">
                {acting ? t.stopping : t.stop}
              </button>
            )}
          </div>
        </div>
        {preview.status === "failed" && (
          <Notice tone="error">
            {t.composeFailed(preview.error ?? "")}{" "}
            <button type="button" onClick={() => act(() => composeVideo(project.id))} className="font-semibold underline underline-offset-2">
              {t.tryAgain}
            </button>
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
      ? t.narrationNone
      : sources.size > 1
        ? t.narrationMixed
        : sources.has("professor")
          ? voiced.length === scenes.length
            ? t.narrationYours
            : t.narrationPartial
          : t.narrationAi;
  const hasAiVoice = sources.has("ai");
  // Narrated only with the professor's own voice: captions would change nothing.
  const captionsUnused = voiced.length > 0 && !hasAiVoice;

  const recordDisabled = acting || project.narrating || busyScenes.length > 0 || preview.status !== "done" || project.preview_outdated;
  const aiDisabled = acting || project.narrating || (voiced.length === scenes.length && !sources.has("professor") && !voiceFailed);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-4">
        <div className="stage rounded-2xl shadow-[0_24px_48px_-28px_rgb(15_20_27/0.6)] ring-1 ring-black/5">
          <Player key={cutUrl(project.id, kind, cut)} src={cutUrl(project.id, kind, cut)} onPausedAt={setPlayerAt} />
        </div>
        <Timeline cut={cut} busy={busyIds} />
        <div className="space-y-2" aria-live="polite">
          {changing.length > 0 && (
            <Notice tone="warn">
              {t.changing(changing.join(", "), phaseLabel(busyScenes, t))}{" "}
              <button type="button" onClick={() => act(() => cancelProject(project.id))} disabled={acting} className="font-semibold underline underline-offset-2">
                {t.stop}
              </button>
            </Notice>
          )}
          {changing.length === 0 && updating && <Notice tone="info">{t.updatingVideo}</Notice>}
          {unapplied.map((s) => (
            <Notice key={s.id} tone="warn">
              {t.unapplied(rangeOf(cut, s.id) ?? t.onePart)}
            </Notice>
          ))}
          {failedScenes.length > 0 && busyScenes.length === 0 && (
            <Notice tone="error">
              {t.rebuildFailed}{" "}
              <button type="button" onClick={() => act(() => startRender(project.id))} className="font-semibold underline underline-offset-2">
                {t.tryAgain}
              </button>
            </Notice>
          )}
          {cutFailed && (
            <Notice tone="error">
              {t.composeFailed(project[cutFailed].error ?? "")}{" "}
              <button type="button" onClick={() => act(() => composeVideo(project.id))} className="font-semibold underline underline-offset-2">
                {t.tryAgain}
              </button>
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

      <aside className="space-y-6 lg:sticky lg:top-6 lg:self-start">
        <section className="panel space-y-4 p-5" aria-labelledby="narration-heading">
          <div>
            <h2 id="narration-heading" className="font-serif text-2xl font-semibold">
              {t.narration}
            </h2>
            <p className="mt-0.5 flex items-center gap-2 text-sm text-muted" aria-live="polite">
              {project.narrating && <span className="pulse-soft h-2 w-2 rounded-full bg-gold" aria-hidden="true" />}
              {project.narrating ? t.generatingAi : narrationLabel}
              {project.narrating && (
                <button type="button" onClick={() => act(() => cancelProject(project.id))} disabled={acting} className="ml-auto font-semibold text-ink underline underline-offset-2">
                  {t.stop}
                </button>
              )}
            </p>
          </div>

          {stale.map((s) => (
            <Notice key={s.id} tone="warn">
              {t.staleChanged(rangeOf(preview, s.id) ?? t.onePart)}{" "}
              <button type="button" onClick={() => setRecordFrom(s.id)} className="font-semibold underline underline-offset-2">
                {t.rerecordFrom(clock(preview.segments.find((g) => g.scene_id === s.id)?.start ?? 0))}
              </button>
            </Notice>
          ))}
          {voiceFailed && !project.narrating && <Notice tone="error">{t.aiFailed}</Notice>}

          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setRecordFrom(firstStart)}
              disabled={recordDisabled}
              className="btn btn-record w-full justify-start gap-3 px-4 py-3 text-left"
            >
              <Icon name="mic" size={20} className="shrink-0" />
              <span>
                {sources.has("professor") ? t.recordAgain : t.recordVoice}
                <span className="block text-xs font-normal text-white/80">{t.recordHint}</span>
              </span>
            </button>
            <div className="overflow-hidden rounded-lg ring-1 ring-rule-strong">
              <button
                type="button"
                onClick={() => {
                  if (sources.has("professor") && !confirm(t.confirmReplace)) return;
                  void act(() => generateAiNarration(project.id));
                }}
                disabled={aiDisabled}
                className="btn btn-secondary w-full justify-start gap-3 rounded-none border-0 px-4 py-3 text-left"
              >
                <Icon name="voice" size={20} className="shrink-0 text-accent" />
                <span>
                  {project.narrating ? t.generating : t.useAi}
                  <span className="block text-xs font-normal text-muted">{t.aiHint}</span>
                </span>
              </button>
              <CaptionsSwitch
                on={project.captions}
                disabled={acting || captionsUnused}
                hint={captionsUnused ? t.captionsNeedAi : t.captionsHint}
                updating={project.captions && hasAiVoice && project.final.status === "building"}
                onToggle={(on) => act(() => setCaptions(project.id, on))}
              />
            </div>
          </div>
          {voiced.length > 0 && (
            <button
              type="button"
              onClick={() => confirm(t.confirmRemove) && act(() => removeNarration(project.id))}
              disabled={acting || project.narrating}
              className="btn btn-ghost -ml-2 text-sm hover:!text-rec"
            >
              <Icon name="trash" size={16} />
              {t.removeNarration}
            </button>
          )}

        </section>

        {project.deck_id && (
          <section className="space-y-3 border-t border-rule pt-6" aria-labelledby="slides-heading">
            <h2 id="slides-heading" className="font-serif text-2xl font-semibold">
              {t.chooseSlides}
            </h2>
            <p className="text-sm text-muted">{t.partOfSlides}</p>
            <button type="button" onClick={() => setEmbedding(true)} disabled={updating || project.preview.version === 0} className="btn btn-primary w-full">
              <Icon name="slides" />
              {t.addToSlides}
            </button>
            {(updating || project.preview.version === 0) && <p className="hint text-center">{t.addToSlidesHint}</p>}
            <Link href={`/decks/${project.deck_id}`} className="btn btn-ghost w-full">
              <Icon name="back" size={16} />
              {t.backToSlides}
            </Link>
          </section>
        )}

        <section className="space-y-3 border-t border-rule pt-6" aria-labelledby="download-heading">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="download-heading" className="font-serif text-2xl font-semibold">
              {t.download}
            </h2>
            {cut.duration > 0 && <span className="text-sm text-muted tabular-nums">{clock(cut.duration)}</span>}
          </div>
          <p className="text-sm text-muted">{kind === "final" ? t.downloadNarrated : t.downloadAnimation}</p>
          <a
            href={updating ? undefined : cutUrl(project.id, kind, cut)}
            download
            aria-disabled={updating}
            className="btn btn-primary w-full"
          >
            <Icon name="download" />
            {updating ? t.updatingVideo : t.downloadMp4}
          </a>
        </section>
      </aside>

      {embedding && project.deck_id && <EmbedDialog project={project} deckId={project.deck_id} onClose={() => setEmbedding(false)} />}
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
