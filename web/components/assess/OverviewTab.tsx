"use client";

import { useState } from "react";

import { AnswerBars, GradeHistogram, ValueBar } from "@/components/assess/charts";
import { Icon } from "@/components/Icon";
import { fmt, fmtGrade, fmtPct, HIGH, WORTH } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import type { Assessment, Question } from "@/lib/types";

const compactKey = (s: string) => s.toLowerCase().replace(/\s+/g, "");

function Kpi({ value, label, strong = false, onClick, className = "" }: { value: string; label: string; strong?: boolean; onClick?: () => void; className?: string }) {
  const figure = `${strong ? "text-4xl" : "text-3xl"} leading-none font-semibold text-ink`;
  return (
    <div className={`flex flex-col-reverse px-5 py-4 ${className}`}>
      <dt className="mt-1.5 text-sm text-muted">{label}</dt>
      <dd>
        {onClick ? (
          <button type="button" onClick={onClick} className={`${figure} rounded underline decoration-rule-strong decoration-2 underline-offset-4 hover:decoration-accent`}>
            {value}
          </button>
        ) : (
          <span className={figure}>{value}</span>
        )}
      </dd>
    </div>
  );
}

function QuestionRow({ a, q, open, onToggle }: { a: Assessment; q: Question; open: boolean; onToggle: () => void }) {
  const { t, lang } = useI18n();
  const qs = a.stats.questions.find((x) => x.question_id === q.id);
  const mistakes = a.analysis.clusters.filter((c) => c.question_id === q.id && c.kind === "mistake");
  const insight = a.analysis.question_insights[q.id];
  const hasDetails = !!(qs && Object.keys(qs.distribution).length) || mistakes.length > 0 || !!insight;
  const pickLabel = (pick: string) => (pick === "—" ? t.asm.blank : q.type === "true_false" ? (pick === "true" ? t.asm.keyTrue : t.asm.keyFalse) : pick);
  const isKey = (pick: string) => compactKey(pick) === compactKey(q.type === "true_false" ? q.answer : q.answer);
  return (
    <li className="border-b border-rule last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        disabled={!hasDetails}
        aria-expanded={hasDetails ? open : undefined}
        className="grid w-full grid-cols-[minmax(0,1fr)] items-center gap-x-4 gap-y-1.5 px-4 py-3 text-left enabled:hover:bg-paper sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_7rem]"
      >
        <span className="flex min-w-0 items-center gap-2">
          {hasDetails ? <Icon name="chevron" size={14} className={`shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`} /> : <span className="w-3.5 shrink-0" />}
          <span className="min-w-0">
            <span className="block font-semibold whitespace-nowrap">{t.asm.questionN(q.label)}</span>
            <span className="block truncate text-xs text-muted">{t.asm.types[q.type]}</span>
          </span>
        </span>
        <ValueBar share={qs?.mean_pct ?? 0} label={fmtPct(qs?.mean_pct ?? null, lang)} />
        <span className="text-sm text-muted tabular-nums sm:text-right">
          {qs && qs.correct_rate !== null && qs.mean_pct !== null && Math.abs(qs.correct_rate - qs.mean_pct) > 0.005 ? t.asm.correctShare(fmtPct(qs.correct_rate, lang)) : ""}
        </span>
      </button>
      {open && hasDetails && (
        <div className="space-y-4 border-t border-rule bg-paper/60 px-4 py-4 sm:pl-10">
          {q.prompt && <p className="text-sm text-muted">{q.prompt}</p>}
          {insight && <p className="text-sm">{insight}</p>}
          {qs && Object.keys(qs.distribution).length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold">{t.asm.answers}</h4>
              <AnswerBars distribution={qs.distribution} isKey={isKey} labelOf={pickLabel} />
            </div>
          )}
          {mistakes.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold">{t.asm.commonMistakes}</h4>
              <ul className="space-y-1 text-sm">
                {mistakes
                  .sort((x, y) => y.members.length - x.members.length)
                  .map((c) => (
                    <li key={c.label} className="flex gap-2">
                      <span className="shrink-0 font-semibold tabular-nums">{c.members.length}×</span>
                      <span>{c.label}</span>
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function OverviewTab({ a, onIntegrity, onReview }: { a: Assessment; onIntegrity: () => void; onReview: () => void }) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState<string | null>(null);
  const s = a.stats;
  const pairs = a.analysis.pairs.filter((p) => p.score >= WORTH).length;
  const aiStrong = a.papers.filter((r) => (r.ai_score ?? 0) >= HIGH).length;
  const alerts = a.papers.filter((r) => r.alerts > 0).length;

  if (s.graded === 0) {
    return <p className="panel px-5 py-8 text-center text-muted">{t.asm.nothingGraded}</p>;
  }
  return (
    <div className="space-y-8">
      <dl className="panel grid grid-cols-2 overflow-hidden sm:grid-cols-5 sm:divide-x sm:divide-rule">
        <Kpi value={`${fmtGrade(s.mean, lang)}`} label={`${t.asm.kpiAverage} / ${a.scale}`} strong />
        <Kpi value={fmtGrade(s.median, lang)} label={t.asm.kpiMedian} />
        <Kpi value={fmtPct(s.pass_rate, lang)} label={t.asm.kpiPassed} />
        <Kpi value={`${s.graded}/${s.total}`} label={t.asm.kpiGraded} />
        <Kpi value={fmt(s.needs_review, lang, 0)} label={t.asm.kpiReview} onClick={onReview} className="col-span-2 border-t border-rule sm:col-span-1 sm:border-t-0" />
      </dl>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start">
        <section aria-labelledby="dist" className="panel p-5">
          <h3 id="dist" className="mb-2 font-serif text-xl font-semibold">
            {t.asm.distribution}
          </h3>
          <GradeHistogram bins={s.histogram} scale={a.scale} />
        </section>
        <section aria-labelledby="insights" className="panel p-5">
          <h3 id="insights" className="font-serif text-xl font-semibold">
            {t.asm.insights}
          </h3>
          {a.analysis.insights ? (
            <>
              <p className="mt-2 leading-relaxed">{a.analysis.insights}</p>
              {a.analysis.recommendations.length > 0 && (
                <>
                  <h4 className="mt-4 text-sm font-semibold">{t.asm.recommendations}</h4>
                  <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm marker:text-accent">
                    {a.analysis.recommendations.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </>
              )}
            </>
          ) : (
            <p className="mt-2 text-muted">{a.analysis.status === "running" ? t.asm.analysing : t.asm.noInsights}</p>
          )}
        </section>
      </div>

      <section aria-labelledby="questions" className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 id="questions" className="font-serif text-xl font-semibold">
            {t.asm.questionsTitle}
          </h3>
          <p className="hint">{t.asm.questionsHint}</p>
        </div>
        <ul className="panel overflow-hidden">
          {a.rubric.questions.map((q) => (
            <QuestionRow key={q.id} a={a} q={q} open={open === q.id} onToggle={() => setOpen(open === q.id ? null : q.id)} />
          ))}
        </ul>
      </section>

      <section aria-labelledby="integrity-glance" className="panel flex flex-wrap items-center gap-x-8 gap-y-3 px-5 py-4">
        <h3 id="integrity-glance" className="flex items-center gap-2 font-semibold">
          <Icon name="shield" size={18} className="text-accent" />
          {t.asm.integrityAtAGlance}
        </h3>
        {pairs || aiStrong || alerts ? (
          <ul className="flex flex-1 flex-wrap gap-x-6 gap-y-1 text-sm">
            {pairs > 0 && <li>{t.asm.pairsToCheck(pairs)}</li>}
            {aiStrong > 0 && <li>{t.asm.aiStrongCount(aiStrong)}</li>}
            {alerts > 0 && <li>{t.asm.alertsCount(alerts)}</li>}
          </ul>
        ) : (
          <p className="flex-1 text-sm text-muted">{t.asm.nothingStandsOut}</p>
        )}
        <button type="button" className="btn btn-secondary py-1.5" onClick={onIntegrity}>
          {t.asm.openIntegrity}
        </button>
      </section>
    </div>
  );
}
