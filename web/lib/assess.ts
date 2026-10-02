/** Pure helpers for the assessment pages: formatting, filtering, sorting, highlighting, ordering. */
import type { UiLang } from "./messages";
import type { Assessment, PairResult, PaperRow, Question, QuestionIn } from "./types";

export const HIGH = 60;
export const WORTH = 30;

const LOCALE: Record<UiLang, string> = { el: "el-GR", en: "en-GB" };

/** A number in the interface language (Greek uses a decimal comma), "—" when there is none. */
export function fmt(value: number | null | undefined, lang: UiLang, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(LOCALE[lang], { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(value);
}

export const fmtGrade = (value: number | null | undefined, lang: UiLang) => fmt(value, lang, 1);

export function fmtPct(value: number | null | undefined, lang: UiLang): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat(LOCALE[lang], { style: "percent", maximumFractionDigits: 0 }).format(value);
}

export function fmtSize(bytes: number, lang: UiLang): string {
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${fmt(v, lang, v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export type CopyLevel = "low" | "worth" | "likely";

export function copyLevel(score: number | null | undefined): CopyLevel {
  const s = score ?? 0;
  return s >= HIGH ? "likely" : s >= WORTH ? "worth" : "low";
}

export const isFlagged = (r: PaperRow) => (r.ai_score ?? 0) >= HIGH || (r.copy_score ?? 0) >= HIGH || r.alerts > 0;
export const displayName = (r: { student_name: string; filename: string }) => r.student_name || r.filename;

export type Filter = "all" | "review" | "flagged" | "failed";

export function filterRows(rows: PaperRow[], filter: Filter, query: string): PaperRow[] {
  const q = fold(query.trim());
  return rows.filter((r) => {
    if (filter === "review" && !r.needs_review) return false;
    if (filter === "flagged" && !isFlagged(r)) return false;
    if (filter === "failed" && r.status !== "failed") return false;
    if (!q) return true;
    return [r.student_name, r.student_id, r.filename].some((v) => fold(v).includes(q));
  });
}

/** Lower case without Greek accents, so "μαρια" finds "Μαρία". */
export function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

export type SortKey = "student" | "status" | "grade" | "ai" | "copy" | "review";
const STATUS_ORDER = { failed: 0, queued: 1, reading: 2, read: 3, grading: 4, graded: 5 } as const;

export function sortRows(rows: PaperRow[], key: SortKey, dir: "asc" | "desc", lang: UiLang): PaperRow[] {
  const collator = new Intl.Collator(LOCALE[lang], { sensitivity: "base", numeric: true });
  const value = (r: PaperRow): number | string => {
    switch (key) {
      case "student":
        return displayName(r);
      case "status":
        return STATUS_ORDER[r.status];
      case "grade":
        return r.grade ?? -1;
      case "ai":
        return r.ai_score ?? -1;
      case "copy":
        return r.copy_score ?? -1;
      case "review":
        return (r.needs_review ? 1000 : 0) + r.review_flags + r.alerts;
    }
  };
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = value(a);
    const vb = value(b);
    const c = typeof va === "string" && typeof vb === "string" ? collator.compare(va, vb) : Number(va) - Number(vb);
    return c !== 0 ? c * sign : collator.compare(displayName(a), displayName(b));
  });
}

export interface Progress {
  total: number;
  read: number;
  graded: number;
  failed: number;
  reading: boolean;
  grading: boolean;
}

/** How far the papers are: read counts every paper past reading; graded counts papers graded with this rubric. */
export function progressOf(a: Assessment): Progress {
  const rows = a.papers;
  const past = new Set(["read", "grading", "graded"]);
  const graded = rows.filter((r) => r.status === "graded" && r.rubric_version === a.rubric.version).length;
  return {
    total: rows.length,
    read: rows.filter((r) => past.has(r.status)).length,
    graded,
    failed: rows.filter((r) => r.status === "failed").length,
    reading: rows.some((r) => r.status === "queued" || r.status === "reading"),
    grading: a.rubric.status === "confirmed" && rows.some((r) => r.status === "grading" || r.status === "read" || (r.status === "graded" && r.rubric_version !== a.rubric.version)),
  };
}

export type Segment = { text: string; mark: boolean };

/** Split `text` into marked and unmarked runs wherever one of `passages` occurs (whitespace- and case-insensitive). */
export function markPassages(text: string, passages: string[]): Segment[] {
  const ranges: [number, number][] = [];
  for (const passage of passages) {
    const words = passage.trim().split(/\s+/).filter(Boolean).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    if (words.length < 2) continue;
    const re = new RegExp(words.join("\\s+"), "giu");
    for (const m of text.matchAll(re)) {
      if (m.index !== undefined && m[0]) ranges.push([m.index, m.index + m[0].length]);
    }
  }
  if (!ranges.length) return text ? [{ text, mark: false }] : [];
  ranges.sort((x, y) => x[0] - y[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([...r]);
  }
  const out: Segment[] = [];
  let at = 0;
  for (const [s, e] of merged) {
    if (s > at) out.push({ text: text.slice(at, s), mark: false });
    out.push({ text: text.slice(s, e), mark: true });
    at = e;
  }
  if (at < text.length) out.push({ text: text.slice(at), mark: false });
  return out;
}

/** The pair score of two papers (0 when the analysis kept no pair for them). */
export function pairScore(pairs: PairResult[], a: string, b: string): number {
  const [x, y] = a < b ? [a, b] : [b, a];
  return pairs.find((p) => p.a === x && p.b === y)?.score ?? 0;
}

/** Order papers so that similar ones sit next to each other (greedy chaining from the strongest pair). */
export function orderForMatrix(ids: string[], pairs: PairResult[]): string[] {
  const score = (a: string, b: string) => pairScore(pairs, a, b);
  const linked = new Set(pairs.flatMap((p) => [p.a, p.b]));
  const order: string[] = [];
  const left = new Set(ids.filter((id) => linked.has(id)));
  const sorted = [...pairs].sort((p, q) => q.score - p.score);
  while (left.size) {
    const seed = sorted.find((p) => left.has(p.a) || left.has(p.b));
    let current = seed ? (left.has(seed.a) ? seed.a : seed.b) : [...left][0];
    left.delete(current);
    order.push(current);
    for (;;) {
      let best: string | null = null;
      let bestScore = 0;
      for (const id of left) {
        const s = score(current, id);
        if (s > bestScore) {
          best = id;
          bestScore = s;
        }
      }
      if (!best) break;
      left.delete(best);
      order.push(best);
      current = best;
    }
  }
  return [...order, ...ids.filter((id) => !linked.has(id))];
}

export function toInput(questions: Question[]): QuestionIn[] {
  return questions.map((q) => ({ ...q, criteria: q.criteria.map((c) => ({ ...c })) }));
}

export function blankQuestion(label: string): QuestionIn {
  return { id: null, label, type: "open", prompt: "", points: 1, options: [], answer: "", tolerance: 0, model_answer: "", criteria: [], partial: false, key_from: "professor" };
}

export const criteriaTotal = (q: Pick<QuestionIn, "criteria">) => q.criteria.reduce((s, c) => s + (Number(c.points) || 0), 0);
export const rubricTotal = (questions: Pick<QuestionIn, "points">[]) => questions.reduce((s, q) => s + (Number(q.points) || 0), 0);

/** The next label after the last one: "3" → "4", "2β" → "2γ", "Θέμα 5" → "Θέμα 6", anything else → its count + 1. */
export function nextLabel(labels: string[]): string {
  const last = labels[labels.length - 1];
  if (!last) return "1";
  const num = last.match(/^(.*?)(\d+)$/);
  if (num) return `${num[1]}${Number(num[2]) + 1}`;
  const greek = "αβγδεζηθικλμνξοπρστυφχψω";
  const tail = last.slice(-1);
  const i = greek.indexOf(tail);
  if (i >= 0 && i < greek.length - 1) return last.slice(0, -1) + greek[i + 1];
  const latin = "abcdefghijklmnopqrstuvwxyz";
  const j = latin.indexOf(tail);
  if (j >= 0 && j < latin.length - 1) return last.slice(0, -1) + latin[j + 1];
  return String(labels.length + 1);
}

/** The papers before and after `id` in `order`. */
export function neighbours(order: string[], id: string): { prev: string | null; next: string | null; index: number } {
  const i = order.indexOf(id);
  return { prev: i > 0 ? order[i - 1] : null, next: i >= 0 && i < order.length - 1 ? order[i + 1] : null, index: i };
}
