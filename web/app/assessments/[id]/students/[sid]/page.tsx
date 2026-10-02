"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PaperIntegrity, Transcript } from "@/components/assess/PaperPanels";
import { PaperViewer, type PaperViewerHandle } from "@/components/assess/PaperViewer";
import { QuestionCard } from "@/components/assess/QuestionCard";
import { Icon } from "@/components/Icon";
import { displayName, fmt, fmtGrade, neighbours } from "@/lib/assess";
import { deletePaper, getPaper, retryPaper, updatePaper } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Assessment, Paper, PaperUpdate, ResultOverride } from "@/lib/types";
import { recallOrder, useAssessment } from "@/lib/useAssessment";

const TABS = ["grading", "integrity", "transcript"] as const;
type Tab = (typeof TABS)[number];
const BUSY = new Set(["queued", "reading", "grading"]);

export default function PaperPage() {
  return (
    <Suspense fallback={null}>
      <PaperLoader />
    </Suspense>
  );
}

function PaperLoader() {
  const { id, sid } = useParams<{ id: string; sid: string }>();
  const { t } = useI18n();
  const { assessment, error: aError, refresh } = useAssessment(id);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPaper(id, sid)
      .then((p) => !cancelled && setPaper(p))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [id, sid]);

  const busy = paper ? BUSY.has(paper.status) : false;
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => {
      getPaper(id, sid).then(setPaper).catch(() => undefined);
    }, 2500);
    return () => clearInterval(timer);
  }, [busy, id, sid]);

  const err = error ?? aError;
  if (err && (!paper || !assessment))
    return (
      <p className="notice notice-error mx-auto max-w-6xl" role="alert">
        {err}
      </p>
    );
  if (!paper || !assessment || paper.id !== sid)
    return (
      <p className="mx-auto max-w-6xl text-muted" aria-live="polite">
        {t.loading}
      </p>
    );
  return <PaperWorkspace key={paper.id} a={assessment} paper={paper} onPaper={setPaper} onAssessment={refresh} />;
}

function totals(a: Assessment, paper: Paper) {
  let points = 0;
  for (const q of a.rubric.questions) {
    const r = paper.results.find((x) => x.question_id === q.id);
    if (r) points += Math.min(q.points, r.override_points ?? r.points);
  }
  const max = a.rubric.questions.reduce((s, q) => s + q.points, 0);
  return { points, max, grade: max ? Math.round((points / max) * a.scale * 10 + 1e-9) / 10 : null };
}

function PaperWorkspace({ a, paper, onPaper, onAssessment }: { a: Assessment; paper: Paper; onPaper: (p: Paper) => void; onAssessment: () => Promise<void> }) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const viewer = useRef<PaperViewerHandle>(null);
  const [tab, setTab] = useState<Tab>(TABS.includes(params.get("tab") as Tab) ? (params.get("tab") as Tab) : "grading");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState(paper.note);

  const order = useMemo(() => {
    const ids = new Set(a.papers.map((r) => r.id));
    const remembered = recallOrder(a.id)?.filter((x) => ids.has(x));
    return remembered && remembered.includes(paper.id) ? remembered : a.papers.map((r) => r.id);
  }, [a.id, a.papers, paper.id]);
  const nav = neighbours(order, paper.id);
  const go = useCallback((target: string | null) => target && router.push(`/assessments/${a.id}/students/${target}${tab !== "grading" ? `?tab=${tab}` : ""}`), [a.id, router, tab]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
      if (e.key === "[") go(nav.prev);
      if (e.key === "]") go(nav.next);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, nav.prev, nav.next]);

  async function save(body: PaperUpdate) {
    setSaving(true);
    setError(null);
    try {
      onPaper(await updatePaper(a.id, paper.id, body));
      void onAssessment();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!window.confirm(t.asm.confirmRemovePaper(displayName(paper)))) return;
    setSaving(true);
    try {
      await deletePaper(a.id, paper.id);
      router.push(`/assessments/${a.id}?tab=students`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  }

  const patchResult = (qid: string) => (o: ResultOverride) => save({ results: { [qid]: o } });
  const sum = totals(a, paper);
  const graded = paper.results.length > 0;
  const results = a.rubric.questions.map((q) => ({ q, r: paper.results.find((x) => x.question_id === q.id) })).filter((x) => x.r);

  return (
    <div className="-mx-4 -my-8 flex flex-col sm:-mx-6 sm:-my-10 lg:h-[calc(100dvh-3.5rem-1px)]">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule bg-paper px-4 py-2.5 sm:px-6">
        <Link href={`/assessments/${a.id}?tab=students`} className="btn btn-ghost -ml-2 py-1.5 text-sm">
          <Icon name="back" size={16} />
          <span className="hidden sm:inline">{t.asm.back}</span>
        </Link>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="student-name">
            {t.asm.studentName}
          </label>
          <input
            id="student-name"
            key={`n-${paper.student_name}`}
            defaultValue={paper.student_name}
            placeholder={t.asm.namePlaceholder}
            onBlur={(e) => e.currentTarget.value.trim() !== paper.student_name && void save({ student_name: e.currentTarget.value })}
            onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            className="min-w-[12rem] flex-1 rounded-md border border-transparent bg-transparent px-1.5 py-1 font-serif text-2xl font-semibold hover:border-rule focus:border-accent focus:bg-surface focus:outline-none sm:max-w-md"
          />
          <label className="sr-only" htmlFor="student-id">
            {t.asm.studentId}
          </label>
          <input
            id="student-id"
            key={`i-${paper.student_id}`}
            defaultValue={paper.student_id}
            placeholder={t.asm.idPlaceholder}
            onBlur={(e) => e.currentTarget.value.trim() !== paper.student_id && void save({ student_id: e.currentTarget.value })}
            onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            className="w-40 rounded-md border border-transparent bg-transparent px-1.5 py-1 text-sm text-muted tabular-nums hover:border-rule focus:border-accent focus:bg-surface focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1">
          <span className="mr-1 text-sm text-muted tabular-nums" title={t.asm.keysHint}>
            {t.asm.paperOf(nav.index + 1, order.length)}
          </span>
          <button type="button" className="btn-icon" disabled={!nav.prev} onClick={() => go(nav.prev)} aria-label={t.asm.previous} title={`${t.asm.previous} ( [ )`}>
            <Icon name="prev" />
          </button>
          <button type="button" className="btn-icon" disabled={!nav.next} onClick={() => go(nav.next)} aria-label={t.asm.next} title={`${t.asm.next} ( ] )`}>
            <Icon name="next" />
          </button>
          <button type="button" className="btn-icon hover:text-danger-ink" disabled={saving} onClick={() => void remove()} aria-label={t.asm.removePaper} title={t.asm.removePaper}>
            <Icon name="trash" size={17} />
          </button>
          <button
            type="button"
            disabled={saving || !graded}
            aria-pressed={paper.reviewed}
            onClick={() => void save({ reviewed: !paper.reviewed })}
            className={`btn ml-2 py-1.5 text-sm ${paper.reviewed ? "btn-secondary border-good text-good" : "btn-primary"}`}
          >
            <Icon name="check" size={16} />
            {paper.reviewed ? t.asm.reviewed : t.asm.markReviewed}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <section className="flex h-[70dvh] min-w-0 flex-col border-b border-rule lg:h-auto lg:min-h-0 lg:w-[52%] lg:border-r lg:border-b-0" aria-label={displayName(paper)}>
          <PaperViewer ref={viewer} aid={a.id} paper={paper} />
        </section>
        <section className="flex min-w-0 flex-col bg-surface lg:min-h-0 lg:flex-1">
          <div role="tablist" aria-label={displayName(paper)} className="flex gap-1 border-b border-rule px-4">
            {TABS.map((name) => (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={tab === name}
                onClick={() => setTab(name)}
                className={`-mb-px border-b-2 px-3 py-2.5 text-sm font-semibold ${tab === name ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"}`}
              >
                {t.asm.paperTabs[name]}
              </button>
            ))}
          </div>
          <div className="px-4 py-5 sm:px-6 lg:min-h-0 lg:flex-1 lg:overflow-y-auto" role="tabpanel">
            {error && (
              <p className="notice notice-error mb-4" role="alert">
                {error}
              </p>
            )}
            {tab === "grading" && (
              <div className="space-y-5">
                {paper.status === "failed" && (
                  <div className="notice notice-error items-center">
                    <span className="flex-1">{t.asm.paperFailed(paper.error ?? "")}</span>
                    <button type="button" className="btn btn-secondary py-1.5" onClick={() => void retryPaper(a.id, paper.id).then(onPaper)}>
                      <Icon name="retry" size={15} />
                      {t.asm.retry}
                    </button>
                  </div>
                )}
                {graded ? (
                  <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
                    <p>
                      <span className="text-5xl leading-none font-semibold">{fmtGrade(sum.grade, lang)}</span>
                      <span className="ml-1.5 text-lg text-muted">/ {a.scale}</span>
                    </p>
                    <p className="pb-1 text-sm text-muted tabular-nums">{t.asm.gradeLine(fmt(sum.points, lang), fmt(sum.max, lang))}</p>
                    {saving && <p className="pb-1 text-sm text-muted">{t.asm.saving}</p>}
                  </div>
                ) : (
                  paper.status !== "failed" && <p className="text-muted">{a.rubric.status === "confirmed" ? t.asm.status[paper.status] : t.asm.readWaiting}</p>
                )}
                {paper.summary && (
                  <p className="leading-relaxed">
                    <span className="font-semibold">{t.asm.summaryLabel}: </span>
                    {paper.summary}
                  </p>
                )}
                <ol className="space-y-3">
                  {results.map(({ q, r }) => (
                    <QuestionCard key={q.id} q={q} r={r!} onPatch={patchResult(q.id)} onShowPage={(n) => viewer.current?.show(n)} />
                  ))}
                </ol>
                <div>
                  <label htmlFor="paper-note" className="label">
                    {t.asm.noteLabel}
                  </label>
                  <textarea
                    id="paper-note"
                    rows={3}
                    value={note}
                    onChange={(e) => setNote(e.currentTarget.value)}
                    onBlur={() => note !== paper.note && void save({ note })}
                    className="field text-sm"
                  />
                </div>
              </div>
            )}
            {tab === "integrity" && <PaperIntegrity a={a} paper={paper} />}
            {tab === "transcript" && <Transcript paper={paper} onShowPage={(n) => viewer.current?.show(n)} />}
          </div>
        </section>
      </div>
    </div>
  );
}
