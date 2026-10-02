"use client";

import { useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { fmtSize } from "@/lib/assess";
import { useI18n } from "@/lib/i18n";
import { mergeFiles } from "@/lib/upload";

const SHOWN = 8;

/** Drop zone and list for many students' papers (PDF/JPG/PNG). */
export function PaperDrop({ files, onFiles, id = "papers", compact = false }: { files: File[]; onFiles: (files: File[]) => void; id?: string; compact?: boolean }) {
  const { t, lang } = useI18n();
  const [over, setOver] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const size = files.reduce((s, f) => s + f.size, 0);
  const shown = showAll ? files : files.slice(0, SHOWN);

  return (
    <div>
      <label
        htmlFor={id}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          onFiles(mergeFiles(files, Array.from(e.dataTransfer.files)));
        }}
        className={
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 text-center transition-colors focus-within:outline-2 focus-within:outline-accent " +
          (compact ? "py-5 " : "py-8 ") +
          (over ? "border-accent bg-accent-soft" : "border-rule-strong bg-surface hover:border-accent")
        }
      >
        <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-soft text-accent">
          <Icon name="upload" size={20} />
        </span>
        <span className="text-sm font-semibold text-ink">{t.asm.papersDrop}</span>
        <span className="hint max-w-xs">{t.asm.papersHint}</span>
        <input
          ref={input}
          id={id}
          type="file"
          multiple
          accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png"
          className="sr-only"
          onChange={(e) => {
            const picked = Array.from(e.currentTarget.files ?? []);
            e.currentTarget.value = "";
            onFiles(mergeFiles(files, picked));
          }}
        />
      </label>
      {files.length > 0 && (
        <div className="mt-3">
          <div className="flex items-center justify-between gap-2 text-sm">
            <span className="font-medium tabular-nums">{t.asm.filesSummary(files.length, fmtSize(size, lang))}</span>
            <button type="button" className="btn btn-ghost py-1 text-sm" onClick={() => onFiles([])}>
              {t.asm.clearFiles}
            </button>
          </div>
          <ul className="mt-1.5 max-h-64 space-y-1 overflow-y-auto">
            {shown.map((f) => (
              <li key={`${f.name}|${f.size}`} className="flex items-center gap-2 rounded-md bg-sunken px-3 py-1.5 text-sm">
                <Icon name="file" size={16} className="shrink-0 text-accent" />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <span className="shrink-0 text-xs text-muted tabular-nums">{fmtSize(f.size, lang)}</span>
                <button
                  type="button"
                  aria-label={t.asm.removeFile(f.name)}
                  className="text-muted hover:text-ink"
                  onClick={() => onFiles(files.filter((x) => x !== f))}
                >
                  <Icon name="close" size={16} />
                </button>
              </li>
            ))}
          </ul>
          {files.length > SHOWN && (
            <button type="button" className="btn btn-ghost mt-1 py-1 text-sm" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
              {showAll ? t.asm.showFewer : t.asm.showAllFiles(files.length)}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
