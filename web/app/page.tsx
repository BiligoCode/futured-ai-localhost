"use client";

import Link from "next/link";

import { AssessmentTile } from "@/components/assess/AssessmentTile";
import { DeckTile } from "@/components/deck/DeckTile";
import { Icon, type IconName } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { ProjectTile } from "@/components/ProjectTile";
import { CurveSketch } from "@/components/Stage";
import { fmt } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import type { AssessmentSummary, DeckSummary, Project } from "@/lib/types";
import { useLibrary } from "@/lib/useLibrary";

type Item = { kind: "project"; at: string; p: Project } | { kind: "deck"; at: string; d: DeckSummary } | { kind: "assessment"; at: string; a: AssessmentSummary };

const RECENT = 6;

function QuickStart() {
  const { t } = useI18n();
  const items: { href: string; label: string; icon: IconName }[] = [
    { href: "/new/animation", label: t.quickAnimation, icon: "film" },
    { href: "/new/slides", label: t.quickSlides, icon: "slides" },
    { href: "/new/assessment", label: t.quickAssessment, icon: "exam" },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((i) => (
        <Link key={i.href} href={i.href} className="btn btn-secondary">
          <Icon name={i.icon} size={16} className="text-accent" />
          {i.label}
        </Link>
      ))}
    </div>
  );
}

/** One line of the stats ledger: a figure and what it counts; links to the section. */
function Stat({ value, label, href, tone }: { value: number; label: string; href: string; tone?: "warn" }) {
  const { lang } = useI18n();
  return (
    <Link href={href} className="group flex flex-col gap-1 px-5 py-4 hover:bg-paper focus-visible:outline-offset-[-2px]">
      <span className="flex items-center gap-2 text-3xl leading-none font-semibold text-ink">
        {fmt(value, lang, 0)}
        {tone === "warn" && value > 0 && <span className="h-2 w-2 rounded-full bg-warn" aria-hidden="true" />}
      </span>
      <span className="text-sm text-muted group-hover:text-ink">{label}</span>
    </Link>
  );
}

export default function Overview() {
  const { t, lang } = useI18n();
  const { projects, decks, assessments, error } = useLibrary();
  const loaded = projects !== null && decks !== null && assessments !== null;

  const items: Item[] = loaded
    ? [
        ...projects.map((p) => ({ kind: "project" as const, at: p.created_at, p })),
        ...decks.map((d) => ({ kind: "deck" as const, at: d.updated_at, d })),
        ...assessments.map((a) => ({ kind: "assessment" as const, at: a.updated_at, a })),
      ].sort((x, y) => y.at.localeCompare(x.at))
    : [];
  const graded = (assessments ?? []).reduce((s, a) => s + a.graded, 0);
  const toReview = (assessments ?? []).reduce((s, a) => s + a.needs_review, 0);
  const working = [
    ...(assessments ?? []).filter((a) => a.busy || (a.papers > 0 && a.rubric_status !== "confirmed")),
  ];
  const creating = (projects ?? []).filter((p) => p.stage === "scenes" && p.preview.version === 0);

  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <PageHeader title={t.overviewTitle} subtitle={t.overviewSubtitle}>
        <QuickStart />
      </PageHeader>

      {error && (
        <p className="notice notice-error" role="alert">
          {t.loadError(error)}
        </p>
      )}
      {!loaded && !error && (
        <p className="text-muted" aria-live="polite">
          {t.loading}
        </p>
      )}

      {loaded && items.length === 0 && (
        <div className="stage stage-grid grid gap-8 rounded-2xl px-6 py-12 sm:grid-cols-[1fr_minmax(0,22rem)] sm:items-center sm:px-12">
          <div className="max-w-md space-y-4">
            <h2 className="font-serif text-3xl leading-tight font-semibold">{t.emptyTitle}</h2>
            <p className="text-stage-muted">{t.emptyBody}</p>
            <Link href="/new" className="btn btn-primary">
              {t.createFirst}
            </Link>
          </div>
          <CurveSketch className="w-full" />
        </div>
      )}

      {loaded && items.length > 0 && (
        <>
          <dl className="panel grid grid-cols-2 divide-rule overflow-hidden sm:grid-cols-5 sm:divide-x [&>*:last-child]:col-span-2 sm:[&>*:last-child]:col-span-1 [&>*:nth-child(n+3)]:border-t [&>*:nth-child(n+3)]:border-rule sm:[&>*:nth-child(n+3)]:border-t-0">
            <div>
              <dt className="sr-only">{t.nav.animations}</dt>
              <dd>
                <Stat value={projects.length} label={t.statAnimations(projects.length)} href="/animations" />
              </dd>
            </div>
            <div>
              <dt className="sr-only">{t.nav.slides}</dt>
              <dd>
                <Stat value={decks.length} label={t.statDecks(decks.length)} href="/slides" />
              </dd>
            </div>
            <div>
              <dt className="sr-only">{t.nav.assessments}</dt>
              <dd>
                <Stat value={assessments.length} label={t.statAssessments(assessments.length)} href="/assessments" />
              </dd>
            </div>
            <div>
              <dt className="sr-only">{t.statGraded(graded)}</dt>
              <dd>
                <Stat value={graded} label={t.statGraded(graded)} href="/assessments" />
              </dd>
            </div>
            <div>
              <dt className="sr-only">{t.statReview(toReview)}</dt>
              <dd>
                <Stat value={toReview} label={t.statReview(toReview)} href="/assessments" tone="warn" />
              </dd>
            </div>
          </dl>

          {(working.length > 0 || creating.length > 0) && (
            <section aria-labelledby="in-progress" className="space-y-3">
              <h2 id="in-progress" className="font-serif text-2xl font-semibold">
                {t.inProgress}
              </h2>
              <ul className="panel divide-y divide-rule">
                {working.map((a) => {
                  const share = a.papers ? a.graded / a.papers : 0;
                  const label = a.rubric_status !== "confirmed" && a.rubric_status !== "drafting" ? t.asm.rubricToCheck : t.asm.meta(a.graded, a.papers);
                  return (
                    <li key={a.id}>
                      <Link href={`/assessments/${a.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-paper">
                        <Icon name="exam" className="shrink-0 text-accent" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{a.title}</span>
                          <span className="block text-sm text-muted">{label}</span>
                        </span>
                        <span className="hidden w-40 shrink-0 sm:block" aria-hidden="true">
                          <span className="block h-1.5 overflow-hidden rounded-full bg-sunken">
                            <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.round(share * 100)}%` }} />
                          </span>
                        </span>
                        <span className="w-12 shrink-0 text-right text-sm text-muted tabular-nums">{fmt(share * 100, lang, 0)}%</span>
                      </Link>
                    </li>
                  );
                })}
                {creating.map((p) => (
                  <li key={p.id}>
                    <Link href={`/projects/${p.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-paper">
                      <Icon name="film" className="shrink-0 text-accent" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{p.title}</span>
                        <span className="block text-sm text-muted">{t.statusCreating}</span>
                      </span>
                      <span className="h-2 w-2 shrink-0 rounded-full bg-gold pulse-soft" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-labelledby="recent" className="space-y-4">
            <h2 id="recent" className="font-serif text-2xl font-semibold">
              {t.recent}
            </h2>
            <ul className="grid grid-cols-1 gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
              {items.slice(0, RECENT).map((i) =>
                i.kind === "project" ? (
                  <ProjectTile key={`p-${i.p.id}`} p={i.p} />
                ) : i.kind === "deck" ? (
                  <DeckTile key={`d-${i.d.id}`} d={i.d} />
                ) : (
                  <AssessmentTile key={`a-${i.a.id}`} a={i.a} />
                ),
              )}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
