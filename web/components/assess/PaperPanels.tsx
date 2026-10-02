"use client";

import Link from "next/link";

import { SharedQuotes, useEvidenceText } from "@/components/assess/IntegrityTab";
import { ScoreChip } from "@/components/assess/ScoreChip";
import { StudentText } from "@/components/assess/StudentText";
import { Icon } from "@/components/Icon";
import { displayName } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import type { Assessment, Finding, Paper } from "@/lib/types";

const SEVERITY = {
  alert: { icon: "alert", cls: "text-critical" },
  warn: { icon: "alert", cls: "text-warn" },
  info: { icon: "file", cls: "text-faint" },
} as const;

function FindingLine({ f }: { f: Finding }) {
  const { t } = useI18n();
  const s = SEVERITY[f.severity];
  const text = t.asm.findings[f.code]?.(f.detail) ?? f.code;
  const samples = f.code === "hidden_text" && Array.isArray(f.detail.samples) ? (f.detail.samples as { page?: number; text?: string; reason?: string }[]) : [];
  return (
    <li className="flex gap-2.5 text-sm">
      <Icon name={s.icon} size={16} className={`mt-0.5 shrink-0 ${s.cls}`} />
      <div className="min-w-0 space-y-1">
        <p className={f.severity === "alert" ? "font-semibold" : ""}>{text}</p>
        {samples.length > 0 && (
          <ul className="space-y-1">
            {samples.map((x, i) => (
              <li key={i} className="rounded-md bg-critical-soft px-2.5 py-1.5 text-xs text-danger-ink">
                <span className="font-semibold">
                  {t.asm.pageN(x.page ?? 0)} · {t.asm.hiddenReasons[x.reason ?? ""] ?? x.reason}:
                </span>{" "}
                “{x.text}”
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

export function PaperIntegrity({ a, paper }: { a: Assessment; paper: Paper }) {
  const { t } = useI18n();
  const evidenceText = useEvidenceText(a);
  const names = new Map(a.papers.map((r) => [r.id, displayName(r)]));
  const pairs = a.analysis.pairs.filter((p) => p.a === paper.id || p.b === paper.id).sort((x, y) => y.score - x.score).slice(0, 5);
  const ai = paper.ai;
  const f = paper.forensics;
  const meta = f ? Object.entries({ ...f.metadata, ...Object.fromEntries(Object.entries(f.xmp).filter(([k]) => ["CreatorTool", "DocumentID"].includes(k))) }) : [];

  return (
    <div className="space-y-6">
      <p className="text-xs text-muted">{t.asm.caution}</p>

      <section aria-labelledby="ai-h" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="ai-h" className="font-serif text-xl font-semibold">
            {t.asm.aiTitle}
          </h3>
          {ai && <ScoreChip score={ai.score} level={ai.level} kind="ai" showLabel />}
        </div>
        {!ai ? (
          <p className="text-sm text-muted">{t.asm.notGradedYet}</p>
        ) : (
          <>
            <p className="text-xs text-muted">{t.asm.wordsAnalysed(ai.words)}</p>
            {ai.signals.length === 0 ? (
              <p className="text-sm text-muted">{t.asm.noAiPaper}</p>
            ) : (
              <ul className="space-y-2">
                {ai.signals.map((s) => (
                  <li key={s.code} className="grid grid-cols-[minmax(0,1fr)_4rem] items-start gap-3 text-sm">
                    <span>
                      <span className="font-semibold">{t.asm.signalNames[s.code] ?? s.code}</span>
                      <span className="block text-muted">{t.asm.signals[s.code]?.(s.detail) ?? ""}</span>
                    </span>
                    <span className="mt-1.5 h-1.5 rounded-full bg-sunken" aria-hidden="true">
                      <span className="block h-full rounded-full bg-warn" style={{ width: `${Math.round(s.strength * 100)}%` }} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {ai.note && (
              <p className="rounded-md bg-paper px-3 py-2 text-sm">
                <span className="font-semibold">{t.asm.larasNote}: </span>
                {ai.note}
              </p>
            )}
          </>
        )}
      </section>

      <section aria-labelledby="copy-h" className="space-y-3">
        <h3 id="copy-h" className="font-serif text-xl font-semibold">
          {t.asm.bestMatches}
        </h3>
        {pairs.length === 0 ? (
          <p className="text-sm text-muted">{a.analysis.covered.includes(paper.id) ? t.asm.noMatch : t.asm.noInsights}</p>
        ) : (
          <ul className="divide-y divide-rule rounded-lg border border-rule">
            {pairs.map((p) => {
              const other = p.a === paper.id ? p.b : p.a;
              return (
                <li key={other} className="space-y-1.5 px-3 py-3">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <Link href={`/assessments/${a.id}/students/${other}`} className="font-semibold hover:text-accent">
                      {names.get(other)}
                    </Link>
                    <ScoreChip score={p.score} kind="copy" showLabel />
                    {p.verdict && <span className="rounded bg-sunken px-1.5 py-0.5 text-xs">{t.asm.verdicts[p.verdict]}</span>}
                    <Link href={`/assessments/${a.id}/compare/${paper.id}/${other}`} className="ml-auto inline-flex items-center gap-1 text-sm text-accent hover:underline">
                      <Icon name="compare" size={14} />
                      {t.asm.compare}
                    </Link>
                  </div>
                  <ul className="space-y-0.5 text-sm text-muted">
                    {p.evidence
                      .filter((e) => e.code !== "lara_verdict")
                      .slice(0, 3)
                      .map((e, i) => (
                        <li key={i}>{evidenceText(e)}</li>
                      ))}
                  </ul>
                  {p.explanation && <p className="text-sm">{p.explanation}</p>}
                  <SharedQuotes pair={p} first={paper.id} />
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="doc-h" className="space-y-3">
        <h3 id="doc-h" className="font-serif text-xl font-semibold">
          {t.asm.documentsTitle}
        </h3>
        {!f ? (
          <p className="text-sm text-muted">{t.asm.notGradedYet}</p>
        ) : (
          <>
            <p className="text-sm text-muted">{t.asm.kinds[f.kind]}</p>
            {f.findings.length === 0 ? (
              <p className="text-sm text-muted">{t.asm.noFindings}</p>
            ) : (
              <ul className="space-y-2">
                {[...f.findings]
                  .sort((x, y) => ["alert", "warn", "info"].indexOf(x.severity) - ["alert", "warn", "info"].indexOf(y.severity))
                  .map((x, i) => (
                    <FindingLine key={`${x.code}-${i}`} f={x} />
                  ))}
              </ul>
            )}
            {(meta.length > 0 || f.file_id || f.fonts.length > 0) && (
              <details className="rounded-lg border border-rule">
                <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">{t.asm.fileDetails}</summary>
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 border-t border-rule px-3 py-2 text-xs">
                  {meta.map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-muted">{t.asm.metaFields[k] ?? k}</dt>
                      <dd className="break-all">{v}</dd>
                    </div>
                  ))}
                  {f.file_id && (
                    <div className="contents">
                      <dt className="text-muted">{t.asm.fileId}</dt>
                      <dd className="break-all font-mono">{f.file_id}</dd>
                    </div>
                  )}
                  {f.fonts.length > 0 && (
                    <div className="contents">
                      <dt className="text-muted">{t.asm.fonts}</dt>
                      <dd>{f.fonts.join(", ")}</dd>
                    </div>
                  )}
                </dl>
              </details>
            )}
            <p className="text-xs text-muted">{t.asm.watermarkNote}</p>
          </>
        )}
      </section>
    </div>
  );
}

export function Transcript({ paper, onShowPage }: { paper: Paper; onShowPage: (n: number) => void }) {
  const { t } = useI18n();
  if (!paper.reading.length) return <p className="text-sm text-muted">{t.asm.status[paper.status]}</p>;
  return (
    <ol className="space-y-5">
      {paper.reading.map((page) => (
        <li key={page.n} className="space-y-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <button type="button" className="hover:text-accent" onClick={() => onShowPage(page.n)}>
              {t.asm.pageN(page.n)}
            </button>
            <span className="font-normal text-muted">{page.text ? t.asm.typedText : ""}</span>
          </h3>
          {page.text && (
            <p className="rounded-md bg-paper px-3 py-2 text-sm">
              <StudentText text={page.text} />
            </p>
          )}
          {page.blocks.length > 0 && (
            <ul className="space-y-2">
              {page.blocks.map((b, i) => (
                <li key={i} className="rounded-md border border-rule px-3 py-2 text-sm">
                  {b.label && <span className="mr-2 rounded bg-sunken px-1.5 py-0.5 text-xs font-semibold">{b.label}</span>}
                  {b.prompt && <span className="text-xs text-muted">{b.prompt}</span>}
                  <p className="mt-1">
                    <StudentText text={b.text} />
                  </p>
                  {b.final && (
                    <p className="mt-1 text-xs text-muted">
                      {t.asm.answered}: <span className="font-semibold text-ink">{b.final}</span>
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
          {page.notes && (
            <p className="flex gap-2 text-xs text-gold-ink">
              <Icon name="eye" size={14} className="mt-px shrink-0" />
              <span>
                <span className="font-semibold">{t.asm.readerNotes}: </span>
                {page.notes}
              </span>
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
