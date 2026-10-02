"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ScoreChip } from "@/components/assess/ScoreChip";
import { Icon } from "@/components/Icon";
import { displayName, filterRows, type Filter, fmt, fmtGrade, isFlagged, sortRows, type SortKey } from "@/lib/assess";
import { retryPaper } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Assessment, PaperRow } from "@/lib/types";
import { rememberOrder } from "@/lib/useAssessment";

const DOT: Record<PaperRow["status"], string> = {
  queued: "bg-faint",
  reading: "bg-gold pulse-soft",
  read: "bg-heat-1",
  grading: "bg-gold pulse-soft",
  graded: "bg-good",
  failed: "bg-critical",
};

export function StudentsTable({ a, filter, onFilter, onChanged }: { a: Assessment; filter: Filter; onFilter: (f: Filter) => void; onChanged: () => void }) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "student", dir: "asc" });
  const [retrying, setRetrying] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rows = useMemo(() => sortRows(filterRows(a.papers, filter, query), sort.key, sort.dir, lang), [a.papers, filter, query, sort, lang]);
  const names = useMemo(() => new Map(a.papers.map((r) => [r.id, displayName(r)])), [a.papers]);
  const counts: Record<Filter, number> = {
    all: a.papers.length,
    review: a.papers.filter((r) => r.needs_review).length,
    flagged: a.papers.filter(isFlagged).length,
    failed: a.papers.filter((r) => r.status === "failed").length,
  };

  function open(id: string) {
    rememberOrder(a.id, rows.map((r) => r.id));
    router.push(`/assessments/${a.id}/students/${id}`);
  }

  async function retry(id: string) {
    setRetrying(id);
    setError(null);
    try {
      await retryPaper(a.id, id);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRetrying(null);
    }
  }

  function header(key: SortKey, label: string, className = "") {
    const active = sort.key === key;
    return (
      <th scope="col" className={`px-3 py-2.5 font-semibold ${className}`} aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded hover:text-ink"
          onClick={() => setSort({ key, dir: active && sort.dir === "asc" ? "desc" : key === "student" || key === "status" ? "asc" : "desc" })}
          aria-label={t.asm.sortBy(label)}
        >
          {label}
          <Icon name={active && sort.dir === "asc" ? "up" : "down"} size={12} className={active ? "text-ink" : "text-faint opacity-0 group-hover:opacity-100"} />
        </button>
      </th>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1 rounded-lg bg-sunken p-1" role="group" aria-label={t.asm.colStatus}>
          {(["all", "review", "flagged", "failed"] as const).map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => onFilter(f)}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${filter === f ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgb(15_20_27/0.12)]" : "text-muted hover:text-ink"}`}
            >
              {t.asm.filters[f]} <span className="tabular-nums text-muted">{counts[f]}</span>
            </button>
          ))}
        </div>
        <label className="relative min-w-56 flex-1 sm:max-w-xs">
          <span className="sr-only">{t.asm.search}</span>
          <Icon name="search" size={16} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-faint" />
          <input type="search" value={query} onChange={(e) => setQuery(e.currentTarget.value)} placeholder={t.asm.search} className="field py-1.5 pl-9" />
        </label>
      </div>
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      <div className="panel relative overflow-x-auto">
        <table className="w-full min-w-[56rem] text-left text-sm">
          <thead className="group border-b border-rule text-muted">
            <tr>
              {header("student", t.asm.colStudent, "pl-4")}
              {header("status", t.asm.colStatus)}
              {header("grade", t.asm.colGrade, "text-right")}
              <th scope="col" className="px-3 py-2.5 text-right font-semibold">
                {t.asm.colPoints}
              </th>
              {header("ai", t.asm.colAi)}
              {header("copy", t.asm.colCopy)}
              {header("review", t.asm.colReview)}
              <th scope="col" className="px-3 py-2.5 pr-4 text-center font-semibold">
                {t.asm.colReviewed}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {rows.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-paper" onClick={() => open(r.id)}>
                <td className="max-w-[18rem] px-3 py-2.5 pl-4">
                  <div className="relative">
                    {/* In the cell's padding, so that every name stays aligned with its ID line. */}
                    {r.needs_review && !r.reviewed && (
                      <span className="absolute top-1/2 -left-3 h-2 w-2 -translate-y-1/2 rounded-full bg-warn" title={t.asm.filters.review} aria-hidden="true" />
                    )}
                    <Link
                      href={`/assessments/${a.id}/students/${r.id}`}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        open(r.id);
                      }}
                      className="block truncate font-semibold text-ink hover:text-accent"
                    >
                      {displayName(r)}
                      {r.needs_review && !r.reviewed && <span className="sr-only">({t.asm.filters.review})</span>}
                    </Link>
                  </div>
                  <span className="block truncate text-xs text-muted">{[r.student_id, r.student_name ? r.filename : ""].filter(Boolean).join(" · ")}</span>
                </td>
                <td className="px-3 py-2.5">
                  <span className="flex items-center gap-2 whitespace-nowrap">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[r.status]}`} aria-hidden="true" />
                    {r.status === "read" && a.rubric.status !== "confirmed" ? t.asm.readWaiting : t.asm.status[r.status]}
                    {r.status === "failed" && (
                      <button
                        type="button"
                        className="btn btn-secondary ml-1 px-2 py-0.5 text-xs"
                        disabled={retrying === r.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          void retry(r.id);
                        }}
                      >
                        <Icon name="retry" size={13} />
                        {t.asm.retry}
                      </button>
                    )}
                  </span>
                  {r.status === "failed" && r.error && <span className="mt-0.5 block max-w-xs truncate text-xs text-danger-ink" title={r.error}>{r.error}</span>}
                </td>
                <td className="px-3 py-2.5 text-right text-base font-semibold tabular-nums">{r.grade === null ? <span className="text-faint">—</span> : fmtGrade(r.grade, lang)}</td>
                <td className="px-3 py-2.5 text-right text-muted tabular-nums">{r.points === null ? "—" : `${fmt(r.points, lang)}/${fmt(r.max_points, lang)}`}</td>
                <td className="px-3 py-2.5">
                  <ScoreChip score={r.ai_score} level={r.ai_level} kind="ai" />
                </td>
                <td className="px-3 py-2.5">
                  <span className="flex min-w-0 items-center gap-2">
                    <ScoreChip score={r.copy_score} kind="copy" />
                    {r.copy_match && (r.copy_score ?? 0) >= 30 && (
                      <span className="truncate text-xs text-muted" title={t.asm.similarTo(names.get(r.copy_match) ?? "")}>
                        ↔ {names.get(r.copy_match)}
                      </span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <span className="flex items-center gap-2 whitespace-nowrap text-xs">
                    {r.review_flags > 0 && (
                      <span className="inline-flex items-center gap-1" title={t.asm.reviewFlags(r.review_flags)}>
                        <Icon name="eye" size={14} className="text-warn" />
                        <span className="tabular-nums">{r.review_flags}</span>
                        <span className="sr-only">{t.asm.reviewFlags(r.review_flags)}</span>
                      </span>
                    )}
                    {r.alerts > 0 && (
                      <span className="inline-flex items-center gap-1" title={r.findings.map((f) => t.asm.findings[f]?.({}) ?? f).join(", ")}>
                        <Icon name="alert" size={14} className="text-critical" />
                        <span className="tabular-nums">{r.alerts}</span>
                      </span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2.5 pr-4 text-center">
                  {r.reviewed ? (
                    <span title={t.asm.reviewed}>
                      <Icon name="check" size={16} className="inline text-good" />
                      <span className="sr-only">{t.asm.reviewed}</span>
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="px-4 py-8 text-center text-muted">{t.asm.noMatches}</p>}
      </div>
    </div>
  );
}
