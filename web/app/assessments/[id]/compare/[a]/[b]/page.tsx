"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { SharedQuotes, useEvidenceText } from "@/components/assess/IntegrityTab";
import { StatusMark } from "@/components/assess/QuestionCard";
import { ScoreChip } from "@/components/assess/ScoreChip";
import { Icon } from "@/components/Icon";
import { displayName, markPassages } from "@/lib/assess";
import { comparePapers, pageUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Assessment, CompareResult, Paper, Question } from "@/lib/types";
import { useAssessment } from "@/lib/useAssessment";

function Marked({ text, passages }: { text: string; passages: string[] }) {
  return (
    <span className="whitespace-pre-wrap break-words">
      {markPassages(text.replace(/~~[\s\S]*?~~/g, ""), passages).map((s, i) =>
        s.mark ? (
          <mark key={i} className="rounded-sm bg-heat-1/45 px-0.5 text-ink">
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </span>
  );
}

function Side({ paper, q, passages, sameWrong }: { paper: Paper; q: Question; passages: string[]; sameWrong: boolean }) {
  const { t } = useI18n();
  const r = paper.results.find((x) => x.question_id === q.id);
  if (!r) return <p className="text-sm text-faint">—</p>;
  const final = r.override_final ?? r.final;
  return (
    <div className="flex min-w-0 gap-3">
      <StatusMark status={r.status} />
      <div className="min-w-0 flex-1 space-y-1.5 text-sm">
        {q.type !== "open" && (
          <p>
            <span className="text-muted">{t.asm.answered}: </span>
            <span className={`font-semibold ${sameWrong ? "rounded bg-critical-soft px-1 text-danger-ink" : ""}`}>{final ?? t.asm.noAnswerText}</span>
          </p>
        )}
        {r.answer && r.answer.trim() !== (final ?? "").trim() && <Marked text={r.answer} passages={passages} />}
        {!r.answer && q.type === "open" && <p className="text-faint">{t.asm.noAnswerText}</p>}
      </div>
    </div>
  );
}

export default function ComparePage() {
  const { id, a: aId, b: bId } = useParams<{ id: string; a: string; b: string }>();
  const { t } = useI18n();
  const { assessment } = useAssessment(id);
  const [data, setData] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    comparePapers(id, aId, bId)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [id, aId, bId]);

  if (error)
    return (
      <p className="notice notice-error mx-auto max-w-6xl" role="alert">
        {error}
      </p>
    );
  if (!data || !assessment)
    return (
      <p className="mx-auto max-w-6xl text-muted" aria-live="polite">
        {t.loading}
      </p>
    );
  return <Compare a={assessment} data={data} />;
}

function Compare({ a, data }: { a: Assessment; data: CompareResult }) {
  const { t } = useI18n();
  const evidenceText = useEvidenceText(a);
  const { a: pa, b: pb, pair } = data;
  const passages = useMemo(() => {
    const out = new Map<string, string[]>();
    for (const e of pair?.evidence ?? []) {
      if (e.code === "shared_passage" && e.question_id && Array.isArray(e.detail.passages)) out.set(e.question_id, e.detail.passages.map(String));
    }
    return out;
  }, [pair]);
  // What the side-by-side check quoted, highlighted in each paper's own words.
  const quotes = useMemo(() => {
    const out = new Map<string, string[]>();
    for (const s of pair?.shared ?? []) {
      if (!s.question_id) continue;
      for (const [paperId, words] of [[pair?.a, s.a], [pair?.b, s.b]]) {
        const key = `${paperId}:${s.question_id}`;
        out.set(key, [...(out.get(key) ?? []), words ?? ""]);
      }
    }
    return out;
  }, [pair]);
  const marks = (paperId: string, qid: string) => [...(passages.get(qid) ?? []), ...(quotes.get(`${paperId}:${qid}`) ?? [])];
  const sameWrong = useMemo(() => {
    const ids = new Set<string>();
    for (const e of pair?.evidence ?? []) {
      if (e.code === "same_wrong_answers" && Array.isArray(e.detail.questions)) {
        for (const q of e.detail.questions as { question_id?: string }[]) if (q.question_id) ids.add(q.question_id);
      }
    }
    return ids;
  }, [pair]);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <Link href={`/assessments/${a.id}?tab=integrity`} className="btn btn-ghost -ml-2 py-1.5 text-sm">
        <Icon name="back" size={16} />
        {t.asm.back}
      </Link>
      <div className="space-y-2">
        <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">{t.asm.compareTitle}</h1>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-lg">
          <Link href={`/assessments/${a.id}/students/${pa.id}`} className="font-semibold hover:text-accent">
            {displayName(pa)}
          </Link>
          <span className="text-faint">↔</span>
          <Link href={`/assessments/${a.id}/students/${pb.id}`} className="font-semibold hover:text-accent">
            {displayName(pb)}
          </Link>
          {pair && <ScoreChip score={pair.score} kind="copy" showLabel />}
          {pair?.verdict && <span className="rounded bg-sunken px-2 py-0.5 text-sm">{t.asm.verdicts[pair.verdict]}</span>}
        </p>
      </div>

      {pair ? (
        <section aria-labelledby="why" className="panel space-y-2 p-5">
          <h2 id="why" className="font-semibold">
            {t.asm.whyAlike}
          </h2>
          <ul className="space-y-1 text-sm">
            {pair.evidence
              .filter((e) => e.code !== "lara_verdict")
              .map((e, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-faint" aria-hidden="true" />
                  {evidenceText(e)}
                </li>
              ))}
          </ul>
          {pair.explanation && <p className="pt-1">{pair.explanation}</p>}
          <div className="pt-1">
            <SharedQuotes pair={pair} first={pa.id} />
          </div>
          <p className="pt-1 text-xs text-muted">{t.asm.caution}</p>
        </section>
      ) : (
        <p className="notice notice-info">{t.asm.notFlagged}</p>
      )}

      <ol className="panel divide-y divide-rule">
        {a.rubric.questions.map((q) => (
          <li key={q.id} className="space-y-2 px-4 py-4">
            <h3 className="text-sm font-semibold">
              {t.asm.question(q.label)} <span className="font-normal text-muted">· {t.asm.types[q.type]}</span>
            </h3>
            <div className="grid gap-4 md:grid-cols-2">
              <Side paper={pa} q={q} passages={marks(pa.id, q.id)} sameWrong={sameWrong.has(q.id)} />
              <Side paper={pb} q={q} passages={marks(pb.id, q.id)} sameWrong={sameWrong.has(q.id)} />
            </div>
          </li>
        ))}
      </ol>

      <div className="grid gap-4 md:grid-cols-2">
        {[pa, pb].map((p) => (
          <div key={p.id} className="space-y-3">
            <h3 className="font-semibold">{displayName(p)}</h3>
            {p.pages.map((pg) => (
              // eslint-disable-next-line @next/next/no-img-element -- scans straight from the Lara API
              <img key={pg.n} src={pageUrl(a.id, p.id, pg.n, pg.dhash)} alt={t.asm.pageN(pg.n)} width={pg.width} height={pg.height} loading="lazy" className="h-auto w-full rounded-sm bg-surface shadow" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
