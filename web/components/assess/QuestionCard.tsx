"use client";

import { useState } from "react";

import { StudentText } from "@/components/assess/StudentText";
import { Icon } from "@/components/Icon";
import { fmt } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import type { Question, QuestionResult, ResultOverride } from "@/lib/types";

const effective = (r: QuestionResult) => (r.override_points ?? r.points);

/** The examiner's margin mark: ✓ correct, ✗ incorrect, ◐ partly, — blank, ? unreadable (icon, colour and word). */
export function StatusMark({ status }: { status: QuestionResult["status"] }) {
  const { t } = useI18n();
  const style = {
    correct: "bg-good-soft text-good",
    incorrect: "bg-critical-soft text-critical",
    partial: "bg-warn-soft text-warn",
    unanswered: "bg-sunken text-faint",
    unreadable: "bg-warn-soft text-warn",
  }[status];
  return (
    <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${style}`} title={t.asm.resultStatus[status]}>
      {status === "correct" && <Icon name="check" size={18} />}
      {status === "incorrect" && <Icon name="close" size={16} />}
      {status === "partial" && (
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.75" />
          <path d="M8 1.5a6.5 6.5 0 0 1 0 13Z" fill="currentColor" />
        </svg>
      )}
      {status === "unanswered" && <span className="text-lg leading-none font-semibold">—</span>}
      {status === "unreadable" && <span className="text-base leading-none font-bold">?</span>}
      <span className="sr-only">{t.asm.resultStatus[status]}</span>
    </span>
  );
}

function keyText(q: Question, t: ReturnType<typeof useI18n>["t"]): string {
  if (q.type === "true_false") return q.answer === "true" ? t.asm.keyTrue : q.answer === "false" ? t.asm.keyFalse : q.answer;
  return q.answer;
}

export function QuestionCard({ q, r, onPatch, onShowPage }: {
  q: Question;
  r: QuestionResult;
  onPatch: (o: ResultOverride) => Promise<void>;
  onShowPage: (n: number) => void;
}) {
  const { t, lang } = useI18n();
  const [mark, setMark] = useState(fmt(effective(r), lang));
  const [shownMark, setShownMark] = useState(effective(r));
  const [comment, setComment] = useState(r.comment);
  const [shownComment, setShownComment] = useState(r.comment);
  const [commenting, setCommenting] = useState(!!r.comment);
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);

  // The server's values win when they change (a re-grade, another tab), unless the field is being edited.
  if (effective(r) !== shownMark) {
    setShownMark(effective(r));
    setMark(fmt(effective(r), lang));
  }
  if (r.comment !== shownComment) {
    setShownComment(r.comment);
    setComment(r.comment);
  }

  async function patch(o: ResultOverride) {
    setBusy(true);
    try {
      await onPatch(o);
    } finally {
      setBusy(false);
    }
  }

  function commitMark() {
    const text = mark.trim().replace(",", ".");
    if (!text) return void patch({ clear_points: true });
    const value = Number(text);
    if (!Number.isFinite(value) || value < 0) {
      setMark(fmt(effective(r), lang));
      return;
    }
    const clamped = Math.min(q.points, Math.round(value * 4) / 4);
    if (clamped !== effective(r)) void patch({ override_points: clamped });
    else setMark(fmt(clamped, lang));
  }

  const definitive = q.type !== "open";
  const reading = r.override_final ?? r.final;
  const differ = r.flags.includes("readings_differ") && r.override_final === null;
  const otherFlags = r.flags.filter((f) => f !== "readings_differ" && t.asm.flags[f]);
  const answerText = r.answer && r.answer.trim() !== (r.final ?? "").trim() ? r.answer : "";

  return (
    <li className="panel p-4" aria-busy={busy}>
      <div className="flex items-start gap-3">
        <StatusMark status={r.status} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h3 className="font-semibold">{t.asm.questionN(q.label)}</h3>
            <span className="text-sm text-muted">{t.asm.types[q.type]}</span>
            {r.page !== null && (
              <button type="button" className="text-xs text-accent underline-offset-2 hover:underline" onClick={() => onShowPage(r.page!)}>
                {t.asm.showOnPage(r.page)}
              </button>
            )}
          </div>
          {q.prompt && <p className="mt-0.5 line-clamp-2 text-sm text-muted">{q.prompt}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <label className="sr-only" htmlFor={`mark-${q.id}`}>
            {t.asm.markLabel}
          </label>
          <input
            id={`mark-${q.id}`}
            value={mark}
            inputMode="decimal"
            onChange={(e) => setMark(e.currentTarget.value)}
            onBlur={commitMark}
            onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            className={`field w-16 px-2 py-1 text-right text-base font-semibold tabular-nums ${r.override_points !== null ? "border-accent bg-accent-soft" : ""}`}
          />
          <span className="text-sm text-muted tabular-nums">{t.asm.outOf2(fmt(q.points, lang))}</span>
        </div>
      </div>

      <div className="mt-3 space-y-3 pl-11">
        {r.override_points !== null && (
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
            {t.asm.larasMark(fmt(r.points, lang))}
            <button type="button" className="text-accent hover:underline" onClick={() => void patch({ clear_points: true })}>
              {t.asm.resetMark}
            </button>
          </p>
        )}

        {definitive && (
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <div className="flex gap-1.5">
              <dt className="text-muted">{r.override_final !== null ? t.asm.yourReading : t.asm.answered}:</dt>
              <dd className="font-semibold">{reading ? <StudentText text={reading} /> : <span className="text-faint">{t.asm.noAnswerText}</span>}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-muted">{t.asm.keyIs}:</dt>
              <dd className="font-semibold">{keyText(q, t)}</dd>
            </div>
          </dl>
        )}

        {differ && (
          <div className="space-y-2 rounded-lg border border-warn/40 bg-warn-soft px-3 py-2.5">
            <p className="flex items-center gap-2 text-sm font-semibold text-gold-ink">
              <Icon name="eye" size={15} />
              {t.asm.flags.readings_differ}
            </p>
            <div className="flex flex-wrap gap-2">
              {[r.final, r.second_final].map((value, i) => (
                <button
                  key={i}
                  type="button"
                  disabled={busy}
                  onClick={() => void patch({ override_final: value ?? "" })}
                  className="btn btn-secondary py-1 text-sm"
                  title={t.asm.useReading}
                >
                  <span className="text-xs text-muted">{i === 0 ? t.asm.answered : t.asm.secondReading}:</span>
                  <span className="font-semibold">{value || t.asm.noAnswerText}</span>
                </button>
              ))}
              <form
                className="flex items-center gap-1"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (custom.trim()) void patch({ override_final: custom.trim() });
                }}
              >
                <input value={custom} onChange={(e) => setCustom(e.currentTarget.value)} placeholder={t.asm.yourReading} aria-label={t.asm.yourReading} className="field w-32 py-1 text-sm" />
                <button type="submit" className="btn-icon" aria-label={t.asm.useReading} disabled={!custom.trim()}>
                  <Icon name="check" size={16} />
                </button>
              </form>
            </div>
          </div>
        )}
        {r.override_final !== null && (
          <p className="text-xs text-muted">
            <button type="button" className="text-accent hover:underline" onClick={() => void patch({ clear_final: true })}>
              {t.asm.resetMark}
            </button>
          </p>
        )}

        {answerText && (
          <blockquote className="rounded-md border-l-2 border-rule-strong bg-paper px-3 py-2 text-sm">
            <StudentText text={answerText} />
          </blockquote>
        )}
        {!definitive && !answerText && r.status === "unanswered" && <p className="text-sm text-faint">{t.asm.noAnswerText}</p>}

        {r.feedback && <p className="text-sm">{r.feedback}</p>}

        {q.type === "open" && q.criteria.length > 0 && (
          <ul className="space-y-1 text-sm">
            {q.criteria.map((c) => {
              const v = r.criteria[c.id] ?? 0;
              return (
                <li key={c.id} className="flex items-start gap-2">
                  <span className={`mt-0.5 shrink-0 ${v >= 1 ? "text-good" : v > 0 ? "text-warn" : "text-critical"}`} aria-hidden="true">
                    <Icon name={v >= 1 ? "check" : v > 0 ? "minus" : "close"} size={14} />
                  </span>
                  <span className="min-w-0 flex-1">{c.text}</span>
                  <span className="shrink-0 text-muted tabular-nums">
                    {fmt(v * c.points, lang)}/{fmt(c.points, lang)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        {(otherFlags.length > 0 || r.confidence !== "high") && (
          <p className="flex flex-wrap gap-1.5">
            {otherFlags.map((f) => (
              <span key={f} className="inline-flex items-center gap-1 rounded-md bg-warn-soft px-2 py-0.5 text-xs text-gold-ink">
                <Icon name="alert" size={12} />
                {t.asm.flags[f]}
              </span>
            ))}
            {r.confidence !== "high" && <span className="rounded-md bg-sunken px-2 py-0.5 text-xs text-muted">{t.asm.confidence[r.confidence]}</span>}
          </p>
        )}

        {commenting ? (
          <div>
            <label htmlFor={`comment-${q.id}`} className="mb-1 block text-xs font-semibold text-muted">
              {t.asm.commentLabel}
            </label>
            <textarea
              id={`comment-${q.id}`}
              value={comment}
              rows={2}
              onChange={(e) => setComment(e.currentTarget.value)}
              onBlur={() => comment !== r.comment && void patch({ comment })}
              placeholder={t.asm.commentPlaceholder}
              className="field text-sm"
            />
          </div>
        ) : (
          <button type="button" className="text-xs text-muted hover:text-ink" onClick={() => setCommenting(true)}>
            + {t.asm.commentLabel}
          </button>
        )}
      </div>
    </li>
  );
}
