"use client";

import { useId, useState } from "react";

import { Icon } from "@/components/Icon";
import { fmt } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import type { HistogramBin } from "@/lib/types";

function niceMax(n: number): number {
  if (n <= 4) return Math.max(1, n);
  const step = n <= 10 ? 2 : n <= 25 ? 5 : n <= 50 ? 10 : 20;
  return Math.ceil(n / step) * step;
}

/** Grade distribution: one column per tenth of the scale, the pass mark as a labelled rule, a tooltip per column,
 * and the same numbers as a table for screen readers. */
export function GradeHistogram({ bins, scale }: { bins: HistogramBin[]; scale: number }) {
  const { t, lang } = useI18n();
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();
  const W = 640;
  const H = 230;
  const pad = { l: 32, r: 8, t: 22, b: 30 };
  const plotW = W - pad.l - pad.r;
  const plotH = H - pad.t - pad.b;
  const top = niceMax(Math.max(0, ...bins.map((b) => b.count)));
  const ticks = top <= 4 ? Array.from({ length: top + 1 }, (_, i) => i) : [0, top / 2, top];
  const slot = plotW / bins.length;
  const bar = Math.min(24, slot - 6);
  const y = (v: number) => pad.t + plotH - (v / top) * plotH;
  const passX = pad.l + (plotW * (scale / 2)) / scale;
  const label = (b: HistogramBin) => t.asm.distributionLabel(fmt(b.start, lang), fmt(b.end, lang), b.count);

  return (
    <figure className="relative" aria-labelledby={titleId}>
      <figcaption id={titleId} className="sr-only">
        {t.asm.distribution}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={t.asm.distribution}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} className="stroke-sunken" strokeWidth="1" />
            <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" className="fill-muted text-[11px] tabular-nums">
              {fmt(v, lang, 0)}
            </text>
          </g>
        ))}
        <line x1={pad.l} x2={W - pad.r} y1={pad.t + plotH + 0.5} y2={pad.t + plotH + 0.5} className="stroke-rule-strong" strokeWidth="1" />
        {bins.map((b, i) => {
          const h = b.count ? Math.max(4, (b.count / top) * plotH) : 0;
          const x = pad.l + i * slot + (slot - bar) / 2;
          const base = pad.t + plotH;
          return (
            <g key={i}>
              {h > 0 && (
                <path
                  d={`M${x},${base} v${-(h - 4)} q0,-4 4,-4 h${bar - 8} q4,0 4,4 v${h - 4} z`}
                  className={`fill-accent transition-opacity ${hover !== null && hover !== i ? "opacity-45" : ""}`}
                />
              )}
              <text x={pad.l + i * slot + slot / 2} y={H - 10} textAnchor="middle" className="fill-muted text-[10.5px] tabular-nums">
                {fmt(b.start, lang)}–{fmt(b.end, lang)}
              </text>
              <rect
                x={pad.l + i * slot}
                y={pad.t}
                width={slot}
                height={plotH}
                fill="transparent"
                tabIndex={0}
                role="graphics-symbol"
                aria-label={label(b)}
                onPointerEnter={() => setHover(i)}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                className="cursor-default outline-none focus-visible:stroke-accent"
              />
            </g>
          );
        })}
        <line x1={passX} x2={passX} y1={pad.t - 6} y2={pad.t + plotH} className="stroke-ink/50" strokeWidth="1" />
        <text x={passX + 5} y={pad.t - 9} className="fill-muted text-[11px]">
          {t.asm.passMark} {fmt(scale / 2, lang)}
        </text>
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border border-rule bg-surface px-2.5 py-1.5 text-sm shadow-md"
          style={{ left: `${((pad.l + hover * slot + slot / 2) / W) * 100}%`, top: `${(Math.max(pad.t, y(bins[hover].count)) / H) * 100}%` }}
        >
          <span className="block font-semibold tabular-nums">{t.asm.students(bins[hover].count)}</span>
          <span className="block text-xs text-muted tabular-nums">
            {fmt(bins[hover].start, lang)}–{fmt(bins[hover].end, lang)} / {scale}
          </span>
        </div>
      )}
      <table className="sr-only">
        <caption>{t.asm.distribution}</caption>
        <tbody>
          {bins.map((b, i) => (
            <tr key={i}>
              <th scope="row">
                {fmt(b.start, lang)}–{fmt(b.end, lang)}
              </th>
              <td>{b.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** A thin horizontal bar with its value at the tip (one series: no legend; the row label names it). */
export function ValueBar({ share, label, tone = "accent" }: { share: number; label: string; tone?: "accent" | "good" | "muted" }) {
  const fill = tone === "good" ? "bg-good" : tone === "muted" ? "bg-rule-strong" : "bg-accent";
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span className="relative h-2.5 min-w-0 flex-1 rounded-full bg-sunken" aria-hidden="true">
        <span className={`absolute inset-y-0 left-0 rounded-full ${fill}`} style={{ width: `${Math.max(0, Math.min(1, share)) * 100}%` }} />
      </span>
      <span className="w-11 shrink-0 text-right text-sm text-ink tabular-nums">{label}</span>
    </span>
  );
}

/** Answers given to a true/false or multiple-choice question, the correct one marked with a check and a word. */
export function AnswerBars({ distribution, isKey, labelOf }: { distribution: Record<string, number>; isKey: (pick: string) => boolean; labelOf: (pick: string) => string }) {
  const { t, lang } = useI18n();
  const total = Object.values(distribution).reduce((s, n) => s + n, 0) || 1;
  const rows = Object.entries(distribution).sort((x, y) => y[1] - x[1]);
  return (
    <ul className="space-y-1.5">
      {rows.map(([pick, n]) => {
        const key = isKey(pick);
        return (
          <li key={pick} className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] items-center gap-3 text-sm">
            <span className="flex min-w-0 items-center gap-1.5">
              {key ? <Icon name="check" size={14} className="shrink-0 text-good" /> : <span className="w-3.5 shrink-0" />}
              <span className={`truncate ${key ? "font-semibold" : ""}`}>{labelOf(pick)}</span>
              {key && <span className="sr-only">({t.asm.keyIs})</span>}
            </span>
            <ValueBar share={n / total} label={`${fmt(n, lang, 0)}`} tone={key ? "good" : "muted"} />
          </li>
        );
      })}
    </ul>
  );
}
