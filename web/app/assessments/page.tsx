"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { AssessmentTile } from "@/components/assess/AssessmentTile";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { deleteAssessment } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AssessmentSummary } from "@/lib/types";
import { useLibrary } from "@/lib/useLibrary";

export default function Assessments() {
  const { t } = useI18n();
  const { assessments, error, setLib } = useLibrary(["assessments"]);
  const [actionError, setActionError] = useState<string | null>(null);
  const deleting = useRef(new Set<string>());

  async function onDelete(a: AssessmentSummary) {
    if (deleting.current.has(a.id) || !window.confirm(t.asm.confirmDelete(a.title))) return;
    deleting.current.add(a.id);
    setActionError(null);
    try {
      await deleteAssessment(a.id);
      setLib((l) => ({ ...l, assessments: l.assessments?.filter((x) => x.id !== a.id) ?? null }));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      deleting.current.delete(a.id);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageHeader title={t.nav.assessments} subtitle={t.assessmentsSubtitle}>
        <Link href="/new/assessment" className="btn btn-primary">
          <Icon name="plus" size={16} />
          {t.newAssessment}
        </Link>
      </PageHeader>
      {(error || actionError) && (
        <p className="notice notice-error" role="alert">
          {error ? t.loadError(error) : actionError}
        </p>
      )}
      {!assessments && !error && (
        <p className="text-muted" aria-live="polite">
          {t.loading}
        </p>
      )}
      {assessments?.length === 0 && (
        <div className="panel max-w-2xl space-y-3 p-6">
          <h2 className="font-serif text-2xl font-semibold">{t.noAssessments}</h2>
          <p className="text-muted">{t.noAssessmentsBody}</p>
          <Link href="/new/assessment" className="btn btn-primary">
            {t.newAssessment}
          </Link>
        </div>
      )}
      {assessments && assessments.length > 0 && (
        <ul className="grid grid-cols-1 gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {assessments.map((a) => (
            <AssessmentTile key={a.id} a={a} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </div>
  );
}
