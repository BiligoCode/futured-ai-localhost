"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";

import { AssessmentHeader } from "@/components/assess/AssessmentHeader";
import { IntegrityTab } from "@/components/assess/IntegrityTab";
import { OverviewTab } from "@/components/assess/OverviewTab";
import { ProgressStrip } from "@/components/assess/ProgressStrip";
import { RubricEditor } from "@/components/assess/RubricEditor";
import { StudentsTable } from "@/components/assess/StudentsTable";
import { type Filter, WORTH } from "@/lib/assess";
import { resumeAssessment } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAssessment } from "@/lib/useAssessment";

const TABS = ["overview", "students", "rubric", "integrity"] as const;
type Tab = (typeof TABS)[number];

export default function AssessmentPage() {
  return (
    <Suspense fallback={null}>
      <Workspace />
    </Suspense>
  );
}

function Workspace() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const { assessment: a, error, refresh, setAssessment } = useAssessment(id);
  const [filter, setFilter] = useState<Filter>("all");
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ overview: null, students: null, rubric: null, integrity: null });

  const asked = params.get("tab");
  const fallback: Tab = a && a.stats.graded === 0 ? (a.rubric.status === "confirmed" ? "students" : "rubric") : "overview";
  const tab: Tab = TABS.includes(asked as Tab) ? (asked as Tab) : fallback;

  function go(next: Tab, f?: Filter) {
    if (f) setFilter(f);
    router.replace(`/assessments/${id}?tab=${next}`, { scroll: false });
  }

  if (error && !a)
    return (
      <p className="notice notice-error mx-auto max-w-6xl" role="alert">
        {error}
      </p>
    );
  if (!a)
    return (
      <p className="mx-auto max-w-6xl text-muted" aria-live="polite">
        {t.loading}
      </p>
    );

  const counts: Partial<Record<Tab, number>> = {
    students: a.papers.length,
    integrity: a.analysis.pairs.filter((p) => p.score >= WORTH).length + a.papers.filter((r) => r.alerts > 0 || (r.ai_score ?? 0) >= 60).length,
  };
  const rubricAttention = a.rubric.status !== "confirmed" && a.rubric.status !== "drafting";

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <AssessmentHeader a={a} onChange={setAssessment} onUploaded={() => void refresh()} />
      <ProgressStrip
        a={a}
        onRubric={() => go("rubric")}
        onFailed={() => go("students", "failed")}
        onResume={() => void resumeAssessment(a.id).then(setAssessment)}
      />

      <div
        role="tablist"
        aria-label={a.title}
        className="relative flex gap-1 overflow-x-auto border-b border-rule"
        onKeyDown={(e) => {
          const i = TABS.indexOf(tab);
          const next = e.key === "ArrowRight" ? TABS[(i + 1) % TABS.length] : e.key === "ArrowLeft" ? TABS[(i + TABS.length - 1) % TABS.length] : null;
          if (next) {
            e.preventDefault();
            go(next);
            tabRefs.current[next]?.focus();
          }
        }}
      >
        {TABS.map((name) => (
          <button
            key={name}
            ref={(el) => {
              tabRefs.current[name] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${name}`}
            aria-selected={tab === name}
            aria-controls={`panel-${name}`}
            tabIndex={tab === name ? 0 : -1}
            onClick={() => go(name)}
            className={
              "relative -mb-px flex shrink-0 items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors " +
              (tab === name ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink")
            }
          >
            {t.asm.tabs[name]}
            {counts[name] ? <span className="rounded-full bg-sunken px-1.5 text-xs font-medium text-muted tabular-nums">{counts[name]}</span> : null}
            {name === "rubric" && rubricAttention && <span className="h-2 w-2 rounded-full bg-warn" aria-hidden="true" />}
          </button>
        ))}
      </div>

      <div role="tabpanel" id="panel-overview" aria-labelledby="tab-overview" hidden={tab !== "overview"}>
        {tab === "overview" && <OverviewTab a={a} onIntegrity={() => go("integrity")} onReview={() => go("students", "review")} />}
      </div>
      <div role="tabpanel" id="panel-students" aria-labelledby="tab-students" hidden={tab !== "students"}>
        {tab === "students" && <StudentsTable a={a} filter={filter} onFilter={setFilter} onChanged={() => void refresh()} />}
      </div>
      {/* The rubric stays mounted so unsaved edits survive a look at another tab. */}
      <div role="tabpanel" id="panel-rubric" aria-labelledby="tab-rubric" hidden={tab !== "rubric"}>
        <RubricEditor a={a} onChange={setAssessment} />
      </div>
      <div role="tabpanel" id="panel-integrity" aria-labelledby="tab-integrity" hidden={tab !== "integrity"}>
        {tab === "integrity" && <IntegrityTab a={a} onChange={setAssessment} />}
      </div>
    </div>
  );
}
