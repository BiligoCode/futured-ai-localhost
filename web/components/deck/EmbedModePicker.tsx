"use client";

import { useI18n } from "@/lib/i18n";
import type { EmbedMode } from "@/lib/types";

/** Where an animation goes: on the chosen slide, on a new slide after it, or on a new slide at the end. */
export function EmbedModePicker({ mode, onChange }: { mode: EmbedMode; onChange: (mode: EmbedMode) => void }) {
  const { t } = useI18n();
  const modes: { value: EmbedMode; label: string }[] = [
    { value: "append", label: t.embedAppend },
    { value: "new_after", label: t.embedNewAfter },
    { value: "new_end", label: t.embedNewEnd },
  ];
  return (
    <div className="grid auto-cols-fr grid-flow-col gap-1 rounded-lg bg-sunken p-1" role="radiogroup" aria-label={t.embedTitle}>
      {modes.map((m) => (
        <label key={m.value} className="cursor-pointer">
          <input type="radio" name="mode" value={m.value} checked={mode === m.value} onChange={() => onChange(m.value)} className="peer sr-only" />
          <span className="block rounded-md px-3 py-2 text-center text-sm text-muted transition-colors peer-checked:bg-surface peer-checked:font-semibold peer-checked:text-ink peer-checked:shadow-[0_1px_2px_rgb(15_20_27/0.12)] peer-focus-visible:outline-2 peer-focus-visible:outline-accent hover:text-ink">
            {m.label}
          </span>
        </label>
      ))}
    </div>
  );
}
