"use client";

import Link from "next/link";

import { Icon } from "@/components/Icon";
import { useI18n } from "@/lib/i18n";
import type { AnimationRef } from "@/lib/types";

const DOT: Record<AnimationRef["status"], string> = {
  draft: "bg-faint",
  creating: "bg-gold pulse-soft",
  ready: "bg-manim",
  missing: "bg-rec",
};

/** The deck's animations (made from it or embedded in it), each linking to its project page. */
export function AnimationsMenu({ animations, label }: { animations: AnimationRef[]; label: string }) {
  const { t } = useI18n();
  const shown = animations.filter((a) => a.status !== "missing");
  return (
    <details className="group relative inline-block">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-md text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
        {label}
        <Icon name="chevron" size={14} className="transition-transform group-open:rotate-180" />
      </summary>
      <div className="absolute top-full left-0 z-20 mt-2 w-72 rounded-lg border border-rule bg-surface p-1.5 shadow-lg">
        {shown.length === 0 ? (
          <p className="px-2.5 py-2 text-sm text-muted">{t.noAnimationsYet}</p>
        ) : (
          <ul className="max-h-72 overflow-y-auto">
            {shown.map((a) => (
              <li key={a.project_id}>
                <Link href={`/projects/${a.project_id}`} className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-sunken">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[a.status]}`} aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{a.title}</span>
                  <span className="shrink-0 text-xs text-muted">{t.animationStatus[a.status]}</span>
                  {a.embedded && <Icon name="film" size={14} className="shrink-0 text-accent" aria-label={t.embeddedBadge} />}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
