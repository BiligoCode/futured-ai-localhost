"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ScoreChip } from "@/components/assess/ScoreChip";
import { Icon } from "@/components/Icon";
import { displayName, orderForMatrix, pairScore, WORTH } from "@/lib/assess";
import { rerunAnalysis } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Assessment, Evidence, PairResult } from "@/lib/types";

const MAX_MATRIX = 120;
const HEAT = [
  { from: 80, cls: "fill-heat-4", swatch: "bg-heat-4", label: "80–100" },
  { from: 60, cls: "fill-heat-3", swatch: "bg-heat-3", label: "60–79" },
  { from: 30, cls: "fill-heat-2", swatch: "bg-heat-2", label: "30–59" },
  { from: 10, cls: "fill-heat-1", swatch: "bg-heat-1", label: "10–29" },
];
const heatClass = (score: number) => HEAT.find((h) => score >= h.from)?.cls ?? "fill-sunken";
const plain = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();

/** What Lara found in both papers, quoted from each — `first` puts that paper's words first. */
export function SharedQuotes({ pair, first }: { pair: PairResult; first?: string }) {
  const { t } = useI18n();
  const items = pair.shared ?? [];
  if (!items.length) return null;
  return (
    <div className="space-y-0.5 text-sm">
      <p className="font-medium">{t.asm.foundInBoth}</p>
      <ul className="space-y-0.5">
        {items.map((s, i) => {
          const [x, y] = first === pair.b ? [s.b, s.a] : [s.a, s.b];
          return (
            <li key={i} className="flex gap-2">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-faint" aria-hidden="true" />
              <span className="min-w-0 break-words">
                {s.what}
                <span className="text-muted">
                  {" "}
                  — «{x}»{plain(x) === plain(y) ? "" : ` · «${y}»`}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** One sentence per piece of evidence, in the professor's language. */
export function useEvidenceText(a: Assessment) {
  const { t } = useI18n();
  const labels = useMemo(() => new Map(a.rubric.questions.map((q) => [q.id, q.label])), [a.rubric.questions]);
  return (e: Evidence) => {
    const fn = t.asm.evidence[e.code];
    return fn ? fn(e.detail, labels.get(e.question_id ?? "") ?? "?") : e.code;
  };
}

function SimilarityMatrix({ a, ids }: { a: Assessment; ids: string[] }) {
  const { t } = useI18n();
  const router = useRouter();
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null);
  const names = useMemo(() => new Map(a.papers.map((r) => [r.id, displayName(r)])), [a.papers]);
  const order = useMemo(() => orderForMatrix(ids, a.analysis.pairs), [ids, a.analysis.pairs]);
  const n = order.length;
  const cell = Math.max(5, Math.min(26, Math.floor(560 / n)));
  const gap = cell >= 10 ? 2 : 1;
  const size = n * cell;
  const labelW = n <= 40 ? 132 : 0;

  function at(e: React.MouseEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const scale = (size + labelW) / box.width;
    const x = (e.clientX - box.left) * scale - labelW;
    const y = (e.clientY - box.top) * scale;
    const i = Math.floor(y / cell);
    const j = Math.floor(x / cell);
    return i >= 0 && j >= 0 && i < n && j < n && i !== j ? { i, j } : null;
  }

  const hovered = hover ? { a: order[hover.i], b: order[hover.j] } : null;
  return (
    <figure className="space-y-3">
      <div className="relative max-w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${size + labelW} ${size}`}
          style={{ width: Math.min(size + labelW, 720), maxWidth: "100%" }}
          className="h-auto cursor-pointer select-none"
          role="img"
          aria-label={t.asm.matrixTitle}
          onPointerMove={(e) => setHover(at(e))}
          onPointerLeave={() => setHover(null)}
          onClick={(e) => {
            const h = at(e);
            if (h) router.push(`/assessments/${a.id}/compare/${order[h.i]}/${order[h.j]}`);
          }}
        >
          {labelW > 0 &&
            order.map((id, i) => (
              <text key={id} x={labelW - 8} y={i * cell + cell / 2 + 4} textAnchor="end" className={`text-[11px] ${hover?.i === i ? "fill-ink font-semibold" : "fill-muted"}`}>
                {(names.get(id) ?? "").slice(0, 18)}
              </text>
            ))}
          <g transform={`translate(${labelW},0)`}>
            {order.map((ra, i) =>
              order.map((rb, j) => {
                if (i === j) return null;
                const score = pairScore(a.analysis.pairs, ra, rb);
                const active = hover && ((hover.i === i && hover.j === j) || (hover.i === j && hover.j === i));
                return (
                  <rect
                    key={`${i}-${j}`}
                    x={j * cell + gap / 2}
                    y={i * cell + gap / 2}
                    width={cell - gap}
                    height={cell - gap}
                    rx={cell >= 10 ? 2 : 0}
                    className={`${heatClass(score)} ${active ? "stroke-ink" : ""}`}
                    strokeWidth={active ? 1.5 : 0}
                  />
                );
              }),
            )}
          </g>
        </svg>
        {hovered && (
          <div className="pointer-events-none absolute top-2 right-2 rounded-md border border-rule bg-surface px-2.5 py-1.5 text-sm shadow-md">
            <span className="block font-semibold tabular-nums">{pairScore(a.analysis.pairs, hovered.a, hovered.b)}/100</span>
            <span className="block text-xs text-muted">
              {names.get(hovered.a)} ↔ {names.get(hovered.b)}
            </span>
          </div>
        )}
      </div>
      <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-sunken ring-1 ring-rule" aria-hidden="true" />
          {t.asm.legendBelow}
        </span>
        {[...HEAT].reverse().map((h) => (
          <span key={h.label} className="inline-flex items-center gap-1.5">
            <span className={`h-3 w-3 rounded-sm ${h.swatch}`} aria-hidden="true" />
            {h.label}
          </span>
        ))}
        <span className="w-full">{t.asm.matrixHint}</span>
      </figcaption>
    </figure>
  );
}

function PairRow({ a, pair }: { a: Assessment; pair: PairResult }) {
  const { t } = useI18n();
  const text = useEvidenceText(a);
  const names = new Map(a.papers.map((r) => [r.id, displayName(r)]));
  const evidence = pair.evidence.filter((e) => e.code !== "lara_verdict").slice(0, 3);
  return (
    <li className="grid gap-3 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
      <div className="min-w-0 space-y-1.5">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Link href={`/assessments/${a.id}/students/${pair.a}`} className="font-semibold hover:text-accent">
            {names.get(pair.a)}
          </Link>
          <span className="text-faint" aria-hidden="true">
            ↔
          </span>
          <Link href={`/assessments/${a.id}/students/${pair.b}`} className="font-semibold hover:text-accent">
            {names.get(pair.b)}
          </Link>
          <ScoreChip score={pair.score} kind="copy" showLabel />
          {pair.verdict && <span className="rounded bg-sunken px-1.5 py-0.5 text-xs text-ink">{t.asm.verdicts[pair.verdict]}</span>}
        </p>
        <ul className="space-y-0.5 text-sm text-muted">
          {evidence.map((e, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-faint" aria-hidden="true" />
              <span className="min-w-0">{text(e)}</span>
            </li>
          ))}
        </ul>
        {pair.explanation && <p className="text-sm">{pair.explanation}</p>}
        <SharedQuotes pair={pair} />
      </div>
      <Link href={`/assessments/${a.id}/compare/${pair.a}/${pair.b}`} className="btn btn-secondary py-1.5 text-sm">
        <Icon name="compare" size={15} />
        {t.asm.compare}
      </Link>
    </li>
  );
}

export function IntegrityTab({ a, onChange }: { a: Assessment; onChange: (a: Assessment) => void }) {
  const { t } = useI18n();
  const [weaker, setWeaker] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const graded = a.papers.filter((r) => r.status === "graded");
  const strong = a.analysis.pairs.filter((p) => p.score >= WORTH);
  const weak = a.analysis.pairs.filter((p) => p.score < WORTH);
  const ai = a.papers.filter((r) => (r.ai_score ?? 0) >= WORTH && r.ai_level !== "insufficient").sort((x, y) => (y.ai_score ?? 0) - (x.ai_score ?? 0));
  const docs = a.papers.filter((r) => r.findings.length > 0 || r.alerts > 0).sort((x, y) => y.alerts - x.alerts);

  async function rerun() {
    setBusy(true);
    setError(null);
    try {
      onChange(await rerunAnalysis(a.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const status =
    graded.length < 2 ? (
      <p className="notice notice-info">{t.asm.analysisNeedsTwo}</p>
    ) : a.analysis.status === "running" ? (
      <p className="notice notice-info" role="status">
        {t.asm.analysing}
      </p>
    ) : a.analysis.status === "failed" || a.analysis.stale ? (
      <div className={`notice ${a.analysis.status === "failed" ? "notice-error" : "notice-warn"} items-center`}>
        <span className="flex-1">{a.analysis.status === "failed" ? t.asm.analysisFailed(a.analysis.error ?? "") : t.asm.analysisStale}</span>
        <button type="button" className="btn btn-secondary py-1.5" disabled={busy} onClick={() => void rerun()}>
          <Icon name="retry" size={15} />
          {t.asm.rerun}
        </button>
      </div>
    ) : null;

  return (
    <div className="space-y-8">
      <p className="flex gap-3 rounded-lg border border-rule bg-surface px-4 py-3 text-sm text-muted">
        <Icon name="shield" size={18} className="mt-0.5 shrink-0 text-accent" />
        {t.asm.caution}
      </p>
      {status}
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}

      <section aria-labelledby="copying" className="space-y-3">
        <div>
          <h3 id="copying" className="font-serif text-2xl font-semibold">
            {t.asm.copyTitle}
          </h3>
          <p className="mt-1 max-w-3xl text-sm text-muted">{t.asm.copyHint}</p>
        </div>
        {strong.length === 0 && a.analysis.computed_at && <p className="text-muted">{t.asm.noPairs}</p>}
        {(strong.length > 0 || (weaker && weak.length > 0)) && (
          <ul className="panel divide-y divide-rule">
            {[...strong, ...(weaker ? weak : [])].map((p) => (
              <PairRow key={`${p.a}-${p.b}`} a={a} pair={p} />
            ))}
          </ul>
        )}
        {weak.length > 0 && (
          <button type="button" className="btn btn-ghost text-sm" aria-expanded={weaker} onClick={() => setWeaker((w) => !w)}>
            {weaker ? t.asm.hideWeaker : t.asm.showWeaker(weak.length)}
          </button>
        )}
        {graded.length >= 3 && graded.length <= MAX_MATRIX && a.analysis.computed_at && (
          <div className="panel p-5">
            <h4 className="mb-3 font-semibold">{t.asm.matrixTitle}</h4>
            <SimilarityMatrix a={a} ids={graded.map((r) => r.id)} />
          </div>
        )}
      </section>

      <section aria-labelledby="ai-use" className="space-y-3">
        <div>
          <h3 id="ai-use" className="font-serif text-2xl font-semibold">
            {t.asm.aiTitle}
          </h3>
          <p className="mt-1 max-w-3xl text-sm text-muted">{t.asm.aiHint}</p>
        </div>
        {ai.length === 0 ? (
          <p className="text-muted">{t.asm.noAi}</p>
        ) : (
          <ul className="panel divide-y divide-rule">
            {ai.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
                <Link href={`/assessments/${a.id}/students/${r.id}?tab=integrity`} className="min-w-40 font-semibold hover:text-accent">
                  {displayName(r)}
                </Link>
                <ScoreChip score={r.ai_score} level={r.ai_level} kind="ai" showLabel />
                <span className="flex-1 text-sm text-muted">{r.ai_signals.map((c) => t.asm.signalNames[c] ?? c).join(" · ")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="documents" className="space-y-3">
        <div>
          <h3 id="documents" className="font-serif text-2xl font-semibold">
            {t.asm.documentsTitle}
          </h3>
          <p className="mt-1 max-w-3xl text-sm text-muted">{t.asm.documentsHint}</p>
        </div>
        {docs.length === 0 ? (
          <p className="text-muted">{t.asm.noFindings}</p>
        ) : (
          <ul className="panel divide-y divide-rule">
            {docs.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                <Link href={`/assessments/${a.id}/students/${r.id}?tab=integrity`} className="min-w-40 font-semibold hover:text-accent">
                  {displayName(r)}
                </Link>
                <span className="flex flex-1 flex-wrap gap-1.5">
                  {r.findings.map((f) => (
                    <span key={f} className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs ${r.alerts ? "bg-critical-soft text-danger-ink" : "bg-warn-soft text-gold-ink"}`}>
                      <Icon name="alert" size={12} />
                      {t.asm.findingNames[f] ?? f}
                    </span>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted">{t.asm.watermarkNote}</p>
      </section>
    </div>
  );
}
