import { Icon } from "./Icon";

const STEPS = ["Setup", "Script", "Animation", "Review & narrate"] as const;

export function Stepper({ current }: { current: 1 | 2 | 3 | 4 }) {
  return (
    <nav aria-label="Progress">
      <ol className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        {STEPS.map((label, i) => {
          const n = i + 1;
          const state = n < current ? "done" : n === current ? "current" : "todo";
          return (
            <li key={label} className="flex items-center gap-3" aria-current={state === "current" ? "step" : undefined}>
              <span className="flex items-center gap-2">
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
                  {state === "done" && <span className="sr-only"> (done)</span>}
                </span>
              </span>
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
