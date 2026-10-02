"use client";

import Link from "next/link";

import { Icon } from "@/components/Icon";
import { useI18n } from "@/lib/i18n";
import type { DeckSummary } from "@/lib/types";

import { SlideThumb } from "./SlideThumb";

/** A deck on the dashboard: its first slide, small, on paper rather than on the dark stage. */
export function DeckTile({ d, onDelete }: { d: DeckSummary; onDelete?: (d: DeckSummary) => void }) {
  const { t } = useI18n();
  return (
    <li className="group/tile relative">
      <Link href={`/decks/${d.id}`} className="group block rounded-xl focus-visible:outline-offset-4">
        <div className="relative overflow-hidden rounded-xl bg-surface ring-1 ring-black/10 transition-[box-shadow] group-hover:shadow-[0_10px_30px_-12px_rgb(15_20_27/0.45)]">
          <SlideThumb html={d.first_slide_html} className="pointer-events-none" />
          <span className="absolute bottom-2.5 left-2.5 inline-flex items-center gap-1 rounded bg-black/65 px-1.5 py-0.5 text-xs font-medium text-white">
            <Icon name="slides" size={12} />
            {t.chooseSlides}
          </span>
        </div>
        <div className="mt-3 flex items-start justify-between gap-3 px-0.5">
          <div className="min-w-0">
            <h2 className="truncate font-serif text-xl leading-tight font-semibold group-hover:text-accent">{d.title}</h2>
            <p className="mt-0.5 truncate text-sm text-muted">{t.deckMeta(d.slide_count, d.animation_count)}</p>
          </div>
          <span className="mt-1 shrink-0 text-xs font-semibold text-muted" title={t.langName[d.language]}>
            {d.language === "el" ? "ΕΛ" : "EN"}
          </span>
        </div>
        <p className="mt-2 flex items-center gap-2 px-0.5 text-sm text-ink">
          <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
          {t.statusSlides}
        </p>
      </Link>
      {onDelete && (
        <button
          type="button"
          aria-label={t.deleteDeckLabel(d.title)}
          title={t.deleteDeck}
          onClick={() => onDelete(d)}
          className="absolute top-2.5 right-2.5 grid h-8 w-8 place-items-center rounded-md bg-black/60 text-white transition-opacity hover:bg-black/80 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/tile:opacity-100 [@media(hover:hover)]:focus-visible:opacity-100"
        >
          <Icon name="trash" size={16} />
        </button>
      )}
    </li>
  );
}
