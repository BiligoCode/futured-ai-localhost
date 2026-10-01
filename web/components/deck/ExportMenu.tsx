"use client";

import { useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { exportDeck, exportUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { ExportFormat } from "@/lib/types";

/** Export ▾ → PDF / Word. Saves first, builds the file on the server, then triggers the download. */
export function ExportMenu({ deckId, hasAnimations, onBeforeExport, onError }: {
  deckId: string;
  hasAnimations: boolean;
  onBeforeExport: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const details = useRef<HTMLDetailsElement>(null);

  async function run(format: ExportFormat) {
    setBusy(format);
    try {
      await onBeforeExport();
      const { url, filename } = await exportDeck(deckId, format);
      const a = document.createElement("a");
      a.href = exportUrl(url);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (details.current) details.current.open = false;
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const items: { format: ExportFormat; label: string; hint: string }[] = [
    { format: "pdf", label: t.exportPdf, hint: t.exportPdfHint },
    { format: "docx", label: t.exportWord, hint: t.exportWordHint },
  ];

  return (
    <details ref={details} className="group relative">
      <summary className="btn btn-primary cursor-pointer list-none [&::-webkit-details-marker]:hidden" aria-busy={busy !== null}>
        <Icon name="export" size={16} />
        {busy ? t.preparingExport : t.export}
        <Icon name="chevron" size={14} className="transition-transform group-open:rotate-180" />
      </summary>
      <div className="absolute top-full right-0 z-20 mt-2 w-72 rounded-lg border border-rule bg-surface p-1.5 shadow-lg">
        {items.map((item) => (
          <button
            key={item.format}
            type="button"
            disabled={busy !== null}
            onClick={() => void run(item.format)}
            className="flex w-full items-start gap-3 rounded-md px-2.5 py-2 text-left hover:bg-sunken disabled:opacity-50"
          >
            <Icon name="file" size={18} className="mt-0.5 shrink-0 text-accent" />
            <span>
              <span className="block text-sm font-semibold">{item.label}</span>
              <span className="block text-xs text-muted">{item.hint}</span>
            </span>
          </button>
        ))}
        {hasAnimations && <p className="hint border-t border-rule px-2.5 pt-2 pb-1">{t.exportZipHint}</p>}
      </div>
    </details>
  );
}
