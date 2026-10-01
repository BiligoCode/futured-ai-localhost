"use client";

import Link from "next/link";

import { useI18n } from "@/lib/i18n";

import { Icon } from "./Icon";

/** `go` makes a step clickable: a link, or an action (e.g. reopening the script). */
export function Stepper({ current, go = {} }: { current: 1 | 2 | 3 | 4; go?: Partial<Record<number, string | (() => void)>> }) {
  const { t } = useI18n();
  const STEPS = t.steps;
  return (
    <nav aria-label={t.progress}>
      <ol className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        {STEPS.map((label, i) => {
          const n = i + 1;
          const state = n < current ? "done" : n === current ? "current" : "todo";
          const target = go[n];
          const step = "flex items-center gap-2" + (target ? " rounded-md hover:text-accent hover:underline underline-offset-4" : "");
          const wrap = (children: React.ReactNode) =>
            typeof target === "string" ? (
              <Link href={target} className={step}>
                {children}
              </Link>
            ) : target ? (
              <button type="button" onClick={target} className={step}>
                {children}
              </button>
            ) : (
              <span className={step}>{children}</span>
            );
          return (
            <li key={label} className="flex items-center gap-3" aria-current={state === "current" ? "step" : undefined}>
              {wrap(
                <>
                  <span
                    className={
                      "grid h-6 w-6 place-items-center rounded-full text-xs font-semibold tabular-nums " +
                      (state === "done"
                        ? "bg-accent text-white"
                        : state === "current"
                          ? "bg-ink text-white"
                          : "text-faint ring-1 ring-rule-strong ring-inset")
                    }
                  >
                    {state === "done" ? <Icon name="check" size={14} /> : n}
                  </span>
                  <span className={state === "todo" ? "text-muted" : state === "current" ? "font-semibold" : "text-ink"}>
                    {label}
                    {state === "done" && <span className="sr-only"> {t.stepDone}</span>}
                  </span>
                </>,
              )}
              {n < STEPS.length && (
                <span className={`hidden h-px w-10 sm:block ${n < current ? "bg-accent" : "bg-rule-strong"}`} aria-hidden="true" />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
