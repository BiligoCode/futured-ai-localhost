import { describe, expect, it } from "vitest";

import { copyLevel, filterRows, fmt, fmtGrade, fmtPct, fmtSize, markPassages, nextLabel, neighbours, orderForMatrix, sortRows } from "./assess";
import type { PairResult, PaperRow } from "./types";

function row(id: string, over: Partial<PaperRow> = {}): PaperRow {
  return {
    id, filename: `${id}.pdf`, student_name: "", student_id: "", status: "graded", error: null, page_count: 1, points: 5, max_points: 10,
    grade: 5, ai_score: 0, ai_level: "low", ai_signals: [], findings: [], copy_score: 0, copy_match: null, alerts: 0, review_flags: 0, needs_review: false,
    reviewed: false, rubric_version: 1, marks: {}, picks: {}, created_at: "", updated_at: "", ...over,
  };
}

describe("formatting", () => {
  it("uses the decimal comma in Greek", () => {
    expect(fmt(7.25, "el")).toBe("7,25");
    expect(fmt(7.25, "en")).toBe("7.25");
    expect(fmtGrade(7.25, "el")).toBe("7,3");
    expect(fmt(null, "el")).toBe("—");
    expect(fmtPct(0.923, "en")).toBe("92%");
    expect(fmtSize(1536, "en")).toBe("1.5 KB");
    expect(fmtSize(12 * 1024 * 1024, "el")).toBe("12 MB");
  });

  it("names copy levels", () => {
    expect([copyLevel(10), copyLevel(30), copyLevel(59), copyLevel(60), copyLevel(null)]).toEqual(["low", "worth", "worth", "likely", "low"]);
  });
});

describe("filter and sort", () => {
  const rows = [
    row("a", { student_name: "Μαρία Παππά", grade: 9, needs_review: true }),
    row("b", { student_name: "Γιώργος", grade: 4, copy_score: 75 }),
    row("c", { student_name: "", filename: "scan_03.pdf", status: "failed", grade: null }),
  ];

  it("filters by state and folds accents in search", () => {
    expect(filterRows(rows, "review", "").map((r) => r.id)).toEqual(["a"]);
    expect(filterRows(rows, "flagged", "").map((r) => r.id)).toEqual(["b"]);
    expect(filterRows(rows, "failed", "").map((r) => r.id)).toEqual(["c"]);
    expect(filterRows(rows, "all", "μαρια").map((r) => r.id)).toEqual(["a"]);
    expect(filterRows(rows, "all", "SCAN").map((r) => r.id)).toEqual(["c"]);
  });

  it("sorts by grade and by name", () => {
    expect(sortRows(rows, "grade", "desc", "el").map((r) => r.id)).toEqual(["a", "b", "c"]);
    expect(sortRows(rows, "student", "asc", "el").map((r) => r.id)).toEqual(["b", "a", "c"]);
  });
});

describe("markPassages", () => {
  it("marks every occurrence, whitespace and case insensitive", () => {
    const text = "Παίρνουμε  το μεσαίο στοιχείο για pivot. Μετά αναδρομή.";
    expect(markPassages(text, ["το μεσαίο στοιχείο"])).toEqual([
      { text: "Παίρνουμε  ", mark: false },
      { text: "το μεσαίο στοιχείο", mark: true },
      { text: " για pivot. Μετά αναδρομή.", mark: false },
    ]);
    expect(markPassages(text, ["για PIVOT. μετά"])).toHaveLength(3);
    expect(markPassages("abc", [])).toEqual([{ text: "abc", mark: false }]);
  });

  it("merges overlapping passages and escapes regex characters", () => {
    const segs = markPassages("x [9, 4, 7, 1] y", ["[9, 4, 7,", "7, 1]"]);
    expect(segs.filter((s) => s.mark).map((s) => s.text)).toEqual(["[9, 4, 7, 1]"]);
  });
});

describe("orderForMatrix", () => {
  it("chains similar papers together", () => {
    const pairs: PairResult[] = [
      { a: "b", b: "d", score: 80, evidence: [], verdict: "", explanation: "" },
      { a: "d", b: "e", score: 40, evidence: [], verdict: "", explanation: "" },
    ];
    expect(orderForMatrix(["a", "b", "c", "d", "e"], pairs)).toEqual(["b", "d", "e", "a", "c"]);
  });
});

describe("labels and neighbours", () => {
  it("continues numbering", () => {
    expect(nextLabel([])).toBe("1");
    expect(nextLabel(["1", "2"])).toBe("3");
    expect(nextLabel(["2α", "2β"])).toBe("2γ");
    expect(nextLabel(["Θέμα 4"])).toBe("Θέμα 5");
    expect(nextLabel(["1a"])).toBe("1b");
  });

  it("finds the previous and next paper", () => {
    expect(neighbours(["a", "b", "c"], "b")).toEqual({ prev: "a", next: "c", index: 1 });
    expect(neighbours(["a"], "a")).toEqual({ prev: null, next: null, index: 0 });
  });
});
