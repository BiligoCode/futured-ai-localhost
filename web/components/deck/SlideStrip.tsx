"use client";

import { useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { useI18n } from "@/lib/i18n";
import type { Slide } from "@/lib/types";

import { SlideThumb } from "./SlideThumb";

/** Numbered thumbnails: click to go to a slide, drag (or ↑ ↓) to reorder, add after the active one, delete. */
export function SlideStrip({ slides, activeId, onSelect, onMove, onAdd, onDelete, className }: {
  slides: Slide[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onMove: (from: number, to: number) => void;
  onAdd: () => void;
  onDelete: (index: number) => void;
  className?: string;
}) {
  const { t } = useI18n();
  const list = useRef<HTMLOListElement>(null);
  const [drag, setDrag] = useState<{ from: number; over: number } | null>(null);

  function indexAt(clientY: number): number {
    const items = Array.from(list.current?.querySelectorAll<HTMLElement>("[data-index]") ?? []);
    for (const item of items) {
      const r = item.getBoundingClientRect();
      if (clientY < r.top + r.height / 2) return Number(item.dataset.index);
    }
    return items.length - 1;
  }

  return (
    <nav aria-label={t.slidesLabel} className={`flex flex-col ${className ?? ""}`}>
      <ol ref={list} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-4">
        {slides.map((s, i) => {
          const active = s.id === activeId;
          return (
            <li
              key={s.id}
              data-index={i}
              className={`group/thumb relative ${drag && drag.over === i && drag.from !== i ? (drag.from < i ? "border-b-2 border-accent pb-1" : "border-t-2 border-accent pt-1") : ""}`}
            >
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                aria-current={active ? "true" : undefined}
                aria-label={t.slideN(i + 1)}
                className={`block w-full rounded-lg text-left transition-[box-shadow] focus-visible:outline-offset-2 ${
                  active ? "ring-2 ring-accent" : "ring-1 ring-rule hover:ring-rule-strong"
                }`}
              >
                <SlideThumb html={s.html} video={!!s.video} className="pointer-events-none" />
              </button>
              <span className="pointer-events-none absolute top-1.5 left-1.5 rounded bg-ink/75 px-1.5 text-[11px] font-semibold text-white tabular-nums">
                {i + 1}
              </span>
              <div className="absolute top-1 right-1 flex flex-col gap-0.5 opacity-0 transition-opacity group-focus-within/thumb:opacity-100 group-hover/thumb:opacity-100">
                <button
                  type="button"
                  aria-label={t.dragSlide(i + 1)}
                  title={t.dragSlide(i + 1)}
                  className="grid h-6 w-6 cursor-grab place-items-center rounded bg-surface/90 text-muted shadow-sm hover:text-ink active:cursor-grabbing"
                  onPointerDown={(e) => {
                    e.currentTarget.setPointerCapture(e.pointerId);
                    setDrag({ from: i, over: i });
                  }}
                  onPointerMove={(e) => drag && setDrag({ from: drag.from, over: indexAt(e.clientY) })}
                  onPointerUp={() => {
                    if (drag && drag.over !== drag.from) onMove(drag.from, drag.over);
                    setDrag(null);
                  }}
                  onPointerCancel={() => setDrag(null)}
                >
                  <Icon name="grip" size={14} />
                </button>
                <button type="button" aria-label={t.moveSlideUp(i + 1)} title={t.moveSlideUp(i + 1)} disabled={i === 0} onClick={() => onMove(i, i - 1)} className="grid h-6 w-6 place-items-center rounded bg-surface/90 text-muted shadow-sm hover:text-ink disabled:opacity-30">
                  <Icon name="up" size={14} />
                </button>
                <button type="button" aria-label={t.moveSlideDown(i + 1)} title={t.moveSlideDown(i + 1)} disabled={i === slides.length - 1} onClick={() => onMove(i, i + 1)} className="grid h-6 w-6 place-items-center rounded bg-surface/90 text-muted shadow-sm hover:text-ink disabled:opacity-30">
                  <Icon name="down" size={14} />
                </button>
                <button type="button" aria-label={t.deleteSlide(i + 1)} title={t.deleteSlide(i + 1)} disabled={slides.length === 1} onClick={() => onDelete(i)} className="grid h-6 w-6 place-items-center rounded bg-surface/90 text-muted shadow-sm hover:text-rec disabled:opacity-30">
                  <Icon name="trash" size={14} />
                </button>
              </div>
            </li>
          );
        })}
      </ol>
      <div className="border-t border-rule p-3">
        <button type="button" onClick={onAdd} className="btn btn-secondary w-full">
          <Icon name="plus" size={16} />
          {t.addSlide}
        </button>
      </div>
    </nav>
  );
}
