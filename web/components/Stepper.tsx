const STEPS = ["Setup", "Script", "Animation", "Review & narrate"] as const;

export function Stepper({ current }: { current: 1 | 2 | 3 | 4 }) {
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const state = n < current ? "done" : n === current ? "current" : "todo";
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className={
                "grid h-7 w-7 place-items-center rounded-full text-xs font-semibold " +
                (state === "done"
                  ? "bg-indigo-600 text-white"
                  : state === "current"
                    ? "border-2 border-indigo-600 text-indigo-700"
                    : "border border-slate-300 text-slate-400")
              }
              aria-current={state === "current" ? "step" : undefined}
            >
              {state === "done" ? "✓" : n}
            </span>
            <span className={state === "todo" ? "text-slate-400" : "font-medium"}>{label}</span>
            {n < STEPS.length && <span className="mx-1 h-px w-8 bg-slate-300" />}
          </li>
        );
      })}
    </ol>
  );
}
