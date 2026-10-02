"use client";

import Link from "next/link";

import { Icon } from "@/components/Icon";
import { CurveSketch } from "@/components/Stage";
import { cutUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Messages } from "@/lib/messages";
import { clock } from "@/lib/time";
import type { Project } from "@/lib/types";

type Status = { label: string; tone: "draft" | "busy" | "ready" | "done" };

export function projectStatus(p: Project, t: Messages): Status {
  if (p.stage === "storyboard") return { label: t.statusDraft, tone: "draft" };
  if (p.preview.version === 0) return { label: t.statusCreating, tone: "busy" };
  if (p.final.version > 0) return { label: t.statusNarrated, tone: "done" };
  return { label: t.statusReady, tone: "ready" };
}

const DOT = { draft: "bg-faint", busy: "bg-gold pulse-soft", ready: "bg-manim", done: "bg-accent" } as const;

/** A still from inside the animation (Manim scenes open on an empty frame). */
function Poster({ p }: { p: Project }) {
  const cut = p.final.version > 0 ? "final" : "preview";
  const at = Math.min(p[cut].duration * 0.3, 8) || 4;
  return (
    <video
      src={`${cutUrl(p.id, cut, p[cut])}#t=${at.toFixed(1)}`}
      preload="metadata"
      muted
      playsInline
      tabIndex={-1}
      aria-hidden="true"
      className="absolute inset-0 h-full w-full object-cover"
    />
  );
}

/** An animation on the dashboard: a still on the dark stage, title, concept and status. */
export function ProjectTile({ p, onDelete }: { p: Project; onDelete?: (p: Project) => void }) {
  const { t } = useI18n();
  const status = projectStatus(p, t);
  const hasVideo = p.stage !== "storyboard" && p.preview.version > 0;
  const duration = hasVideo ? p[p.final.version > 0 ? "final" : "preview"].duration : 0;
  return (
    <li className="group/tile relative">
      <Link href={`/projects/${p.id}`} className="group block rounded-xl focus-visible:outline-offset-4">
        <div className="stage stage-grid aspect-video rounded-xl ring-1 ring-black/5 transition-[box-shadow] group-hover:shadow-[0_10px_30px_-12px_rgb(15_20_27/0.45)]">
          {hasVideo ? (
            <Poster p={p} />
          ) : (
            <div className="absolute inset-0 grid place-items-center p-6">
              {status.tone === "busy" ? (
                <CurveSketch className="w-3/4" />
              ) : (
                <p className="line-clamp-3 text-center font-serif text-lg leading-snug text-stage-muted italic">{p.concept}</p>
              )}
            </div>
          )}
          {duration > 0 && (
            <span className="absolute right-2.5 bottom-2.5 rounded bg-black/65 px-1.5 py-0.5 text-xs font-medium text-white tabular-nums">
              {clock(duration)}
            </span>
          )}
        </div>
        <div className="mt-3 flex items-start justify-between gap-3 px-0.5">
          <div className="min-w-0">
            <h2 className="truncate font-serif text-xl leading-tight font-semibold group-hover:text-accent">{p.title}</h2>
            <p className="mt-0.5 truncate text-sm text-muted">{p.concept}</p>
          </div>
          <span className="mt-1 flex shrink-0 items-center gap-2 text-xs font-semibold text-muted">
            {p.deck_id && (
              <span className="inline-flex items-center gap-1 rounded bg-sunken px-1.5 py-0.5 text-ink" title={t.fromSlides}>
                <Icon name="slides" size={12} />
                {t.chooseSlides}
              </span>
            )}
            <span title={t.langName[p.language]}>{p.language === "el" ? "ΕΛ" : "EN"}</span>
          </span>
        </div>
        <p className="mt-2 flex items-center gap-2 px-0.5 text-sm text-ink">
          <span className={`h-2 w-2 rounded-full ${DOT[status.tone]}`} aria-hidden="true" />
          {status.label}
        </p>
      </Link>
      {onDelete && (
        <button
          type="button"
          aria-label={t.deleteLabel(p.title)}
          title={t.deleteVideo}
          onClick={() => onDelete(p)}
          className="absolute top-2.5 right-2.5 grid h-8 w-8 place-items-center rounded-md bg-black/60 text-white transition-opacity hover:bg-black/80 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/tile:opacity-100 [@media(hover:hover)]:focus-visible:opacity-100"
        >
          <Icon name="trash" size={16} />
        </button>
      )}
    </li>
  );
}
