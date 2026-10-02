"use client";

import { useState } from "react";

import { Icon } from "@/components/Icon";
import { blankQuestion, criteriaTotal, fmt, nextLabel, rubricTotal, toInput } from "@/lib/assess";
import { draftRubric, saveRubric } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Assessment, QuestionIn, QuestionType } from "@/lib/types";

const TYPES: QuestionType[] = ["true_false", "multiple_choice", "numeric", "short", "open"];
const serverKey = (a: Assessment) => JSON.stringify([a.rubric.status, a.rubric.version, a.rubric.questions]);

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-xs font-semibold text-muted">{label}</span>
      {children}
    </label>
  );
}

function QuestionEditor({ q, index, count, onChange, onRemove, onMove }: {
  q: QuestionIn;
  index: number;
  count: number;
  onChange: (q: QuestionIn) => void;
  onRemove: () => void;
  onMove: (delta: -1 | 1) => void;
}) {
  const { t, lang } = useI18n();
  const set = (patch: Partial<QuestionIn>) => onChange({ ...q, ...patch });
  // Editing the key makes it the professor's: it is no longer flagged as Lara's proposal.
  const setKey = (patch: Partial<QuestionIn>) => onChange({ ...q, ...patch, key_from: "professor" });
  const sum = criteriaTotal(q);
  const label = q.label || String(index + 1);
  return (
    <li className="panel space-y-4 p-4 sm:p-5">
      <div className="flex flex-wrap items-end gap-3">
        <Field label={t.asm.labelLabel}>
          <input value={q.label} onChange={(e) => set({ label: e.currentTarget.value })} className="field w-24 py-1.5 font-semibold" required />
        </Field>
        <Field label={t.asm.typeLabel}>
          <select
            value={q.type}
            onChange={(e) => {
              const type = e.currentTarget.value as QuestionType;
              set({ type, answer: type === q.type ? q.answer : "", key_from: "professor" });
            }}
            className="field py-1.5"
          >
            {TYPES.map((ty) => (
              <option key={ty} value={ty}>
                {t.asm.types[ty]}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t.asm.pointsLabel}>
          <input
            type="number"
            min={0.25}
            step={0.25}
            value={q.points}
            onChange={(e) => set({ points: Number(e.currentTarget.value) })}
            className="field w-24 py-1.5 tabular-nums"
            required
          />
        </Field>
        <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
          {q.key_from === "lara" && (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-warn-soft px-2 py-1 text-xs font-semibold text-gold-ink">
              <Icon name="alert" size={13} />
              {t.asm.keyFromLara}
            </span>
          )}
          {q.key_from === "exam" && (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-sunken px-2 py-1 text-xs text-muted">
              <Icon name="exam" size={13} />
              {t.asm.keyFromExam}
            </span>
          )}
          <span className="flex">
            <button type="button" className="btn-icon" disabled={index === 0} onClick={() => onMove(-1)} aria-label={t.asm.moveQuestionUp(label)}>
              <Icon name="up" size={16} />
            </button>
            <button type="button" className="btn-icon" disabled={index === count - 1} onClick={() => onMove(1)} aria-label={t.asm.moveQuestionDown(label)}>
              <Icon name="down" size={16} />
            </button>
            <button type="button" className="btn-icon hover:text-danger-ink" onClick={onRemove} aria-label={t.asm.deleteQuestion(label)}>
              <Icon name="trash" size={16} />
            </button>
          </span>
        </div>
      </div>

      <Field label={t.asm.promptLabel}>
        <textarea value={q.prompt} onChange={(e) => set({ prompt: e.currentTarget.value })} rows={2} className="field field-sizing-content min-h-[3.5rem]" />
      </Field>

      {q.type === "true_false" && (
        <fieldset>
          <legend className="mb-1 block text-xs font-semibold text-muted">{t.asm.keyLabel}</legend>
          <div className="inline-grid grid-flow-col gap-1 rounded-lg bg-sunken p-1">
            {(["true", "false"] as const).map((v) => (
              <label key={v} className="cursor-pointer">
                <input type="radio" name={`tf-${index}`} checked={q.answer === v} onChange={() => setKey({ answer: v })} className="peer sr-only" />
                <span className="block rounded-md px-4 py-1.5 text-sm text-muted peer-checked:bg-surface peer-checked:font-semibold peer-checked:text-ink peer-checked:shadow-[0_1px_2px_rgb(15_20_27/0.12)] peer-focus-visible:outline-2 peer-focus-visible:outline-accent">
                  {v === "true" ? t.asm.keyTrue : t.asm.keyFalse}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      {q.type === "multiple_choice" && (
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_14rem]">
          <div>
            <span className="mb-1 block text-xs font-semibold text-muted">{t.asm.optionsLabel}</span>
            <ul className="space-y-1.5">
              {q.options.map((o, i) => (
                <li key={i} className="flex items-center gap-2">
                  <input
                    value={o}
                    onChange={(e) => set({ options: q.options.map((x, j) => (j === i ? e.currentTarget.value : x)) })}
                    placeholder={t.asm.optionPlaceholder}
                    aria-label={`${t.asm.optionsLabel} ${i + 1}`}
                    className="field py-1.5"
                  />
                  <button type="button" className="btn-icon shrink-0" onClick={() => set({ options: q.options.filter((_, j) => j !== i) })} aria-label={t.asm.removeOption}>
                    <Icon name="close" size={16} />
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" className="btn btn-ghost mt-1 py-1 text-sm" onClick={() => set({ options: [...q.options, ""] })}>
              <Icon name="plus" size={14} />
              {t.asm.addOption}
            </button>
          </div>
          <Field label={t.asm.correctOption}>
            <input value={q.answer} onChange={(e) => setKey({ answer: e.currentTarget.value })} className="field py-1.5 font-semibold" />
            <span className="hint mt-1 block">{t.asm.correctOptionHint}</span>
          </Field>
        </div>
      )}

      {q.type === "numeric" && (
        <div className="flex flex-wrap items-end gap-4">
          <Field label={t.asm.numberLabel}>
            <input value={q.answer} inputMode="decimal" onChange={(e) => setKey({ answer: e.currentTarget.value })} className="field w-40 py-1.5 font-semibold tabular-nums" />
          </Field>
          <Field label={t.asm.toleranceLabel}>
            <input type="number" min={0} step="any" value={q.tolerance} onChange={(e) => set({ tolerance: Number(e.currentTarget.value) || 0 })} className="field w-28 py-1.5 tabular-nums" />
          </Field>
        </div>
      )}

      {q.type === "short" && (
        <Field label={t.asm.shortKeyLabel}>
          <input value={q.answer} onChange={(e) => setKey({ answer: e.currentTarget.value })} className="field py-1.5 font-semibold" />
          <span className="hint mt-1 block">{t.asm.shortKeyHint}</span>
        </Field>
      )}

      {(q.type === "numeric" || q.type === "short") && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={q.partial} onChange={(e) => set({ partial: e.currentTarget.checked })} className="h-4 w-4 accent-[var(--color-accent)]" />
          {t.asm.partialLabel}
        </label>
      )}

      {(q.type === "open" || q.partial) && (
        <Field label={t.asm.modelAnswerLabel}>
          <textarea value={q.model_answer} onChange={(e) => set({ model_answer: e.currentTarget.value })} rows={3} className="field field-sizing-content min-h-[5rem]" placeholder={t.asm.modelAnswerPlaceholder} />
        </Field>
      )}

      {q.type === "open" && (
        <div>
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs font-semibold text-muted">{t.asm.criteriaLabel}</span>
            {q.criteria.length > 0 && (
              <span className={`text-xs tabular-nums ${Math.abs(sum - q.points) < 0.01 ? "text-muted" : "font-semibold text-gold-ink"}`}>
                {Math.abs(sum - q.points) >= 0.01 && <Icon name="alert" size={12} className="mr-1 inline" />}
                {t.asm.criteriaSum(fmt(sum, lang), fmt(q.points, lang))}
              </span>
            )}
          </div>
          <ul className="space-y-1.5">
            {q.criteria.map((c, i) => (
              <li key={i} className="flex items-center gap-2">
                <input
                  value={c.text}
                  onChange={(e) => set({ criteria: q.criteria.map((x, j) => (j === i ? { ...x, text: e.currentTarget.value } : x)) })}
                  placeholder={t.asm.criterionPlaceholder}
                  aria-label={`${t.asm.criteriaLabel} ${i + 1}`}
                  className="field py-1.5"
                />
                <input
                  type="number"
                  min={0.25}
                  step={0.25}
                  value={c.points}
                  onChange={(e) => set({ criteria: q.criteria.map((x, j) => (j === i ? { ...x, points: Number(e.currentTarget.value) } : x)) })}
                  aria-label={`${t.asm.pointsLabel} ${i + 1}`}
                  className="field w-20 shrink-0 py-1.5 tabular-nums"
                />
                <button type="button" className="btn-icon shrink-0" onClick={() => set({ criteria: q.criteria.filter((_, j) => j !== i) })} aria-label={t.asm.removeCriterion}>
                  <Icon name="close" size={16} />
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="btn btn-ghost mt-1 py-1 text-sm"
            onClick={() => set({ criteria: [...q.criteria, { id: null, text: "", points: Math.max(0.25, q.points - sum) || 1 }] })}
          >
            <Icon name="plus" size={14} />
            {t.asm.addCriterion}
          </button>
        </div>
      )}
    </li>
  );
}

export function RubricEditor({ a, onChange }: { a: Assessment; onChange: (a: Assessment) => void }) {
  const { t, lang } = useI18n();
  const [draft, setDraft] = useState<QuestionIn[]>(() => toInput(a.rubric.questions));
  const [base, setBase] = useState(() => serverKey(a));
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState<"save" | "confirm" | "draft" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A new draft from Lara (or another tab's save) replaces the form, unless the professor is editing it.
  const key = serverKey(a);
  if (!dirty && key !== base) {
    setBase(key);
    setDraft(toInput(a.rubric.questions));
  }

  const edit = (next: QuestionIn[]) => {
    setDraft(next);
    setDirty(true);
  };
  const graded = a.papers.filter((r) => r.status === "graded").length;
  const confirmed = a.rubric.status === "confirmed";

  async function save(confirm: boolean) {
    const proposed = draft.filter((q) => q.key_from === "lara" && q.type !== "open").length;
    if (confirm && proposed > 0 && !window.confirm(t.asm.confirmLaraKeys(proposed))) return;
    setSaving(confirm ? "confirm" : "save");
    setError(null);
    try {
      const updated = await saveRubric(a.id, draft, confirm);
      setDirty(false);
      setBase(serverKey(updated));
      setDraft(toInput(updated.rubric.questions));
      onChange(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  async function redraft() {
    if ((draft.length > 0 || dirty) && !window.confirm(t.asm.confirmRedraft)) return;
    setSaving("draft");
    setError(null);
    try {
      const updated = await draftRubric(a.id);
      setDirty(false);
      onChange(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  const drafting = a.rubric.status === "drafting";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl space-y-1">
          <p className="text-muted">{t.asm.rubricIntro}</p>
          {a.rubric.source !== "manual" && a.rubric.questions.length > 0 && (
            <p className="text-sm text-muted">{a.rubric.source === "exam" ? t.asm.fromExam : t.asm.fromPapers}</p>
          )}
        </div>
        <span className="text-sm text-muted">{confirmed ? t.asm.rubricConfirmed(a.rubric.version) : null}</span>
      </div>
      {a.rubric.note && (
        <div className="notice notice-info">
          <Icon name="sparkle" size={16} className="mt-0.5 shrink-0" />
          <p>
            <span className="font-semibold">{t.asm.noteFromLara}: </span>
            {a.rubric.note}
          </p>
        </div>
      )}
      {drafting && (
        <p className="notice notice-info" role="status">
          {t.asm.drafting}
        </p>
      )}

      {draft.length === 0 && !drafting && <p className="panel px-5 py-8 text-center text-muted">{t.asm.noQuestions}</p>}
      <ol className="space-y-3">
        {draft.map((q, i) => (
          <QuestionEditor
            key={q.id ?? `new-${i}`}
            q={q}
            index={i}
            count={draft.length}
            onChange={(nq) => edit(draft.map((x, j) => (j === i ? nq : x)))}
            onRemove={() => edit(draft.filter((_, j) => j !== i))}
            onMove={(d) => {
              const next = [...draft];
              const [item] = next.splice(i, 1);
              next.splice(i + d, 0, item);
              edit(next);
            }}
          />
        ))}
      </ol>
      <button type="button" className="btn btn-secondary" onClick={() => edit([...draft, blankQuestion(nextLabel(draft.map((q) => q.label)))])}>
        <Icon name="plus" size={16} />
        {t.asm.addQuestion}
      </button>

      <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap items-center gap-3 rounded-xl border border-rule bg-surface/95 px-4 py-3 shadow-[0_-8px_24px_-16px_rgb(15_20_27/0.35)] backdrop-blur">
        <span className="font-semibold tabular-nums">{t.asm.totalPoints(fmt(rubricTotal(draft), lang))}</span>
        {dirty && <span className="text-sm text-gold-ink">{t.asm.unsavedRubric}</span>}
        {error && (
          <span className="text-sm text-danger-ink" role="alert">
            {error}
          </span>
        )}
        <span className="flex-1" />
        <button type="button" className="btn btn-ghost" disabled={saving !== null || drafting} onClick={() => void redraft()}>
          <Icon name="sparkle" size={16} />
          {t.asm.redraft}
        </button>
        <button type="button" className="btn btn-secondary" disabled={saving !== null || drafting || !dirty} onClick={() => void save(false)}>
          {saving === "save" ? t.asm.saving : t.asm.save}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={saving !== null || drafting || draft.length === 0}
          onClick={() => void save(true)}
          title={confirmed && graded ? t.asm.regradeNote(graded) : undefined}
        >
          <Icon name="check" size={16} />
          {saving === "confirm" ? t.asm.saving : confirmed && graded ? t.asm.saveAndRegrade : t.asm.saveAndGrade}
        </button>
        {confirmed && graded > 0 && <p className="hint w-full text-right">{t.asm.regradeNote(graded)}</p>}
      </div>
    </div>
  );
}
