/** Axes and a curve that draws itself, Manim-style: shown while Lara is still making something. */
export function CurveSketch({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 320 140" fill="none" aria-hidden="true" className={className}>
      <g stroke="rgb(141 154 171 / 0.55)" strokeWidth="1.25" strokeLinecap="round">
        <path d="M20 112H300" />
        <path d="M40 128V12" />
      </g>
      <path
        pathLength={1}
        className="curve-draw"
        d="M40 104C78 104 96 26 140 26S196 92 228 92 270 52 300 46"
        stroke="var(--color-manim)"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Lara's mark: a tiny plotted curve on axes. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <rect width="32" height="32" rx="8" fill="var(--color-stage)" />
      <path d="M7 24.5H25.5M8.5 26V7" stroke="var(--color-stage-muted)" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M8.5 22c3.5 0 4.5-12 8.5-12s4 7 8 7" fill="none" stroke="var(--color-manim)" strokeWidth="2.25" strokeLinecap="round" />
    </svg>
  );
}
