"use client";

import { forwardRef, useImperativeHandle, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { pageUrl, sourceUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Paper } from "@/lib/types";

export type PaperViewerHandle = { show: (page: number) => void };

const ZOOMS = [60, 80, 100, 130, 160, 200];

/** The scanned (or rendered) pages, one under the other, with zoom. `show(n)` scrolls page n into view. */
export const PaperViewer = forwardRef<PaperViewerHandle, { aid: string; paper: Paper }>(function PaperViewer({ aid, paper }, ref) {
  const { t } = useI18n();
  const [zoom, setZoom] = useState(2);
  const [active, setActive] = useState<number | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    show(page: number) {
      const el = scroller.current?.querySelector<HTMLElement>(`[data-page="${page}"]`);
      if (el && scroller.current) {
        scroller.current.scrollTo({ top: el.offsetTop - 12, behavior: "smooth" });
        setActive(page);
        window.setTimeout(() => setActive(null), 1600);
      }
    },
  }));

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-rule bg-paper px-3 py-1.5">
        <span className="mr-auto truncate text-xs text-muted">{t.asm.kinds[paper.forensics?.kind ?? "scanned"]}</span>
        <button type="button" className="btn-icon" disabled={zoom === 0} onClick={() => setZoom((z) => Math.max(0, z - 1))} aria-label={t.asm.zoomOut}>
          <Icon name="zoomOut" size={17} />
        </button>
        <button type="button" className="btn btn-ghost px-2 py-1 text-xs tabular-nums" onClick={() => setZoom(2)} title={t.asm.fitWidth}>
          {ZOOMS[zoom]}%
        </button>
        <button type="button" className="btn-icon" disabled={zoom === ZOOMS.length - 1} onClick={() => setZoom((z) => Math.min(ZOOMS.length - 1, z + 1))} aria-label={t.asm.zoomIn}>
          <Icon name="zoomIn" size={17} />
        </button>
        <a href={sourceUrl(aid, paper.id)} target="_blank" rel="noreferrer" className="btn-icon" aria-label={t.asm.openOriginal} title={t.asm.openOriginal}>
          <Icon name="external" size={17} />
        </a>
      </div>
      <div ref={scroller} className="relative min-h-0 flex-1 overflow-auto bg-sunken/70 p-4">
        <div className="mx-auto space-y-4" style={{ width: `${ZOOMS[zoom]}%` }}>
          {paper.pages.map((p) => (
            <figure key={p.n} data-page={p.n} className="space-y-1">
              {/* eslint-disable-next-line @next/next/no-img-element -- scans come straight from the Lara API at reading resolution; an optimiser would blur handwriting */}
              <img
                src={pageUrl(aid, paper.id, p.n, p.dhash)}
                alt={t.asm.pageN(p.n)}
                width={p.width}
                height={p.height}
                loading={p.n > 2 ? "lazy" : "eager"}
                className={`block h-auto w-full rounded-sm bg-surface shadow-[0_2px_10px_-2px_rgb(15_20_27/0.25)] transition-[outline] ${active === p.n ? "outline-4 outline-accent" : ""}`}
              />
              <figcaption className="text-center text-xs text-muted">{t.asm.pageN(p.n)}</figcaption>
            </figure>
          ))}
          {paper.pages.length === 0 && <p className="py-16 text-center text-sm text-muted">{t.asm.status[paper.status]}</p>}
        </div>
      </div>
    </div>
  );
});
