const PATHS = {
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Zm-6.5 9a6.5 6.5 0 0 0 13 0M12 18.5V21",
  voice: "M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2",
  download: "M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19.5h14",
  up: "M12 19V5m0 0-6 6m6-6 6 6",
  down: "M12 5v14m0 0-6-6m6 6 6-6",
  close: "M6 6l12 12M18 6 6 18",
  plus: "M12 5v14M5 12h14",
  play: "M8 5.5v13l10.5-6.5L8 5.5Z",
  pause: "M8.5 5.5v13M15.5 5.5v13",
  pin: "M12 21s6.5-5.6 6.5-11.2A6.5 6.5 0 0 0 5.5 9.8C5.5 15.4 12 21 12 21Zm0-8.7a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Zm0 0v5h5",
  check: "M5 12.5 10 17.5 19 7",
  send: "M5 12h13m0 0-5.5-5.5M18 12l-5.5 5.5",
  back: "M19 12H6m0 0 5.5-5.5M6 12l5.5 5.5",
  trash: "M4.5 7h15M10 11v6m4-6v6M6.5 7l1 12.5a1.5 1.5 0 0 0 1.5 1.5h6a1.5 1.5 0 0 0 1.5-1.5l1-12.5M9.5 7V4.5h5V7",
} as const;

export type IconName = keyof typeof PATHS;

/** A 24px stroke icon. Decorative by default; pair it with visible text or an aria-label on the control. */
export function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  const filled = name === "play";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
