"use client";

import { Icon } from "@/components/Icon";
import { progressOf } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import type { Assessment } from "@/lib/types";

/** What is happening now and what the professor has to do next: rubric to check, papers in progress, failures. */
export function ProgressStrip({ a, onRubric, onFailed, onResume }: { a: Assessment; onRubric: () => void; onFailed: () => void; onResume: () => void }) {
  const { t } = useI18n();
  const p = progressOf(a);
  const r = a.rubric;
  const notices: React.ReactNode[] = [];

  if (a.paused) {
    notices.push(
      <div key="paused" className="notice notice-warn items-center">
        <Icon name="pause" size={16} className="shrink-0" />
        <span className="flex-1">{t.asm.pausedNotice}</span>
        <button type="button" className="btn btn-secondary py-1.5" onClick={onResume}>
          {t.asm.resume}
        </button>
      </div>,
    );
  }
  if (r.status === "drafting") {
    notices.push(
      <div key="drafting" className="notice notice-info items-center" role="status">
        <span className="h-2 w-2 shrink-0 rounded-full bg-accent pulse-soft" aria-hidden="true" />
        <span className="flex-1">{a.exam_chars > 0 || r.source === "exam" ? t.asm.drafting : t.asm.draftingFromPapers}</span>
      </div>,
    );
  } else if (r.status === "draft" || r.status === "failed" || (r.status === "none" && a.papers.length > 0)) {
    const text = r.status === "draft" ? t.asm.rubricReady : r.status === "failed" ? t.asm.rubricFailed(r.error ?? "") : t.asm.rubricNeeded;
    notices.push(
      <div key="rubric" className={`notice ${r.status === "failed" ? "notice-error" : "notice-warn"} items-center`}>
        <Icon name="exam" size={16} className="shrink-0" />
        <span className="flex-1">{text}</span>
        <button type="button" className="btn btn-primary py-1.5" onClick={onRubric}>
          {t.asm.checkRubric}
        </button>
      </div>,
    );
  }
  if (p.failed > 0) {
    notices.push(
      <div key="failed" className="notice notice-error items-center">
        <Icon name="alert" size={16} className="shrink-0" />
        <span className="flex-1">{t.asm.failedNotice(p.failed)}</span>
        <button type="button" className="btn btn-secondary py-1.5" onClick={onFailed}>
          {t.asm.showFailed}
        </button>
      </div>,
    );
  }

  const working = !a.paused && (p.reading || p.grading || a.analysis.status === "running");
  return (
    <div className="space-y-3">
      {working && p.total > 0 && (
        <div className="panel flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3" role="status" aria-live="polite">
          <span className="h-2 w-2 rounded-full bg-gold pulse-soft" aria-hidden="true" />
          <span className="text-sm tabular-nums">{t.asm.progressReading(p.read, p.total)}</span>
          {r.status === "confirmed" && <span className="text-sm tabular-nums">{t.asm.progressGrading(p.graded, p.total)}</span>}
          {a.analysis.status === "running" && <span className="text-sm">{t.asm.progressAnalysing}</span>}
          <div className="h-1.5 min-w-40 flex-1 overflow-hidden rounded-full bg-sunken" aria-hidden="true">
            <div className="relative h-full">
              <div className="absolute inset-y-0 left-0 rounded-full bg-heat-1 transition-[width]" style={{ width: `${(p.read / p.total) * 100}%` }} />
              <div className="absolute inset-y-0 left-0 rounded-full bg-accent transition-[width]" style={{ width: `${(p.graded / p.total) * 100}%` }} />
            </div>
          </div>
        </div>
      )}
      {notices}
    </div>
  );
}
