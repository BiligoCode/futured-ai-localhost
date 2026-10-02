"use client";

import Link from "next/link";

import { Icon } from "@/components/Icon";
import { fmtGrade } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import type { AssessmentSummary } from "@/lib/types";

/** The class's grade distribution as the tile's picture: ten columns over the scale, the pass mark as a rule. */
export function GradeSketch({ counts, scale, className }: { counts: number[]; scale: number; className?: string }) {
  const max = Math.max(1, ...counts);
  const w = 200;
  const h = 64;
  const slot = w / 10;
  const bar = Math.min(12, slot - 2);
  return (
    <svg viewBox={`0 0 ${w} ${h + 2}`} className={className} aria-hidden="true">
      <line x1="0" x2={w} y1={h + 0.5} y2={h + 0.5} className="stroke-rule-strong" strokeWidth="1" />
      {counts.map((c, i) => {
        const bh = c ? Math.max(3, (c / max) * (h - 6)) : 0;
        const x = i * slot + (slot - bar) / 2;
        return bh ? (
          <path
            key={i}
            d={`M${x},${h} v${-(bh - 3)} q0,-3 3,-3 h${bar - 6} q3,0 3,3 v${bh - 3} z`}
            className="fill-accent"
          />
        ) : null;
      })}
      <line x1={w / 2} x2={w / 2} y1="2" y2={h} className="stroke-ink/35" strokeWidth="1" />
      <title>{`0–${scale}`}</title>
    </svg>
  );
}

/** A stack of papers: the tile picture before anything is graded. */
function PaperStack({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 80" className={className} aria-hidden="true" fill="none">
      <rect x="30" y="14" width="56" height="62" rx="3" className="fill-sunken stroke-rule-strong" transform="rotate(-6 58 45)" />
      <rect x="34" y="10" width="56" height="62" rx="3" className="fill-surface stroke-rule-strong" transform="rotate(4 62 41)" />
      <rect x="32" y="8" width="56" height="62" rx="3" className="fill-surface stroke-rule-strong" />
      <path d="M40 22h28M40 30h36M40 38h32M40 46h24" className="stroke-faint" strokeWidth="2" strokeLinecap="round" />
      <path d="M66 52l5 5 10-11" className="stroke-good" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function AssessmentTile({ a, onDelete }: { a: AssessmentSummary; onDelete?: (a: AssessmentSummary) => void }) {
  const { t, lang } = useI18n();
  const graded = a.graded > 0;
  const state = a.paused
    ? { label: t.asm.pausedBadge, dot: "bg-faint" }
    : a.rubric_status !== "confirmed" && a.rubric_status !== "drafting" && a.papers > 0
      ? { label: t.asm.rubricToCheck, dot: "bg-warn" }
      : a.busy
        ? { label: t.asm.working, dot: "bg-gold pulse-soft" }
        : a.needs_review
          ? { label: t.asm.toReview(a.needs_review), dot: "bg-warn" }
          : { label: t.asm.meta(a.graded, a.papers), dot: "bg-good" };
  return (
    <li className="group/tile relative">
      <Link href={`/assessments/${a.id}`} className="group block rounded-xl focus-visible:outline-offset-4">
        <div className="relative aspect-video overflow-hidden rounded-xl bg-surface ring-1 ring-black/10 transition-[box-shadow] group-hover:shadow-[0_10px_30px_-12px_rgb(15_20_27/0.45)]">
          {graded ? (
            <div className="absolute inset-0 flex flex-col justify-between p-4 pb-3">
              <p className="text-ink">
                <span className="text-4xl leading-none font-semibold">{fmtGrade(a.mean, lang)}</span>
                <span className="ml-1 text-sm text-muted">/ {a.scale}</span>
              </p>
              <GradeSketch counts={a.histogram} scale={a.scale} className="h-[45%] w-full" />
            </div>
          ) : (
            <div className="absolute inset-0 grid place-items-center">
              <PaperStack className="w-2/5" />
            </div>
          )}
          <span className="absolute top-3 right-3 inline-flex items-center gap-1 rounded bg-black/65 px-1.5 py-0.5 text-xs font-medium text-white">
            <Icon name="exam" size={12} />
            {t.asm.papersCount(a.papers)}
          </span>
        </div>
        <div className="mt-3 flex items-start justify-between gap-3 px-0.5">
          <div className="min-w-0">
            <h2 className="truncate font-serif text-xl leading-tight font-semibold group-hover:text-accent">{a.title}</h2>
            <p className="mt-0.5 truncate text-sm text-muted">{a.course || t.asm.meta(a.graded, a.papers)}</p>
          </div>
          <span className="mt-1 shrink-0 text-xs font-semibold text-muted" title={t.langName[a.language]}>
            {a.language === "el" ? "ΕΛ" : "EN"}
          </span>
        </div>
        <p className="mt-2 flex items-center gap-2 px-0.5 text-sm text-ink">
          <span className={`h-2 w-2 rounded-full ${state.dot}`} aria-hidden="true" />
          {state.label}
          {a.flagged > 0 && (
            <span className="inline-flex items-center gap-1 text-critical">
              <Icon name="alert" size={13} />
              <span className="text-ink">{t.asm.flaggedCount(a.flagged)}</span>
            </span>
          )}
        </p>
      </Link>
      {onDelete && (
        <button
          type="button"
          aria-label={t.asm.deleteLabel(a.title)}
          title={t.asm.deleteAssessment}
          onClick={() => onDelete(a)}
          className="absolute top-2.5 left-2.5 grid h-8 w-8 place-items-center rounded-md bg-black/60 text-white transition-opacity hover:bg-black/80 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/tile:opacity-100 [@media(hover:hover)]:focus-visible:opacity-100"
        >
          <Icon name="trash" size={16} />
        </button>
      )}
    </li>
  );
}
