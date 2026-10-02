"use client";

import { Icon } from "@/components/Icon";
import { copyLevel, HIGH, WORTH } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import type { AiLevel } from "@/lib/types";

/** An AI-likeness or copying score: the number, a status mark from 30 up and the level in words (never colour alone). */
export function ScoreChip({ score, kind, level, showLabel = false }: { score: number | null; kind: "ai" | "copy"; level?: AiLevel | null; showLabel?: boolean }) {
  const { t } = useI18n();
  if (score === null || score === undefined) return <span className="text-faint">—</span>;
  const label =
    kind === "ai" ? t.asm.levels[level ?? (score >= HIGH ? "strong" : score >= WORTH ? "some" : "low")] : t.asm.copyLevels[copyLevel(score)];
  const insufficient = kind === "ai" && level === "insufficient";
  const tone = insufficient || score < WORTH ? "low" : score >= HIGH ? "high" : "mid";
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap" title={label}>
      {tone === "high" && <Icon name="alert" size={14} className="text-critical" />}
      {tone === "mid" && <span className="h-2 w-2 rounded-full bg-warn" aria-hidden="true" />}
      <span className={`tabular-nums ${tone === "low" ? "text-muted" : "font-semibold text-ink"}`}>{insufficient ? "—" : score}</span>
      {showLabel ? <span className="text-sm text-muted">{label}</span> : <span className="sr-only">{label}</span>}
    </span>
  );
}
