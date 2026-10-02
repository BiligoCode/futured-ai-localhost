"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { deleteAssessment, exportAssessment, exportUrl, pauseAssessment, resumeAssessment, updateAssessment } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Assessment } from "@/lib/types";
import { mergeFiles, uploadInBatches, type UploadOutcome } from "@/lib/upload";

function closeMenu(menu: HTMLDetailsElement | null) {
  if (menu) menu.open = false;
}

/** Title (click to rename), what it is, and the actions: add papers, export, pause/resume, delete. */
export function AssessmentHeader({ a, onChange, onUploaded }: { a: Assessment; onChange: (a: Assessment) => void; onUploaded: () => void }) {
  const { t } = useI18n();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<{ done: number; total: number } | null>(null);
  const [result, setResult] = useState<UploadOutcome | null>(null);
  const exportMenu = useRef<HTMLDetailsElement>(null);
  const moreMenu = useRef<HTMLDetailsElement>(null);

  async function rename(title: string) {
    setEditing(false);
    const next = title.trim();
    if (!next || next === a.title) return;
    try {
      onChange(await updateAssessment(a.id, { title: next }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function addPapers(files: File[]) {
    if (!files.length) return;
    setError(null);
    setResult(null);
    const out = await uploadInBatches(a.id, files, null, (done, total) => setUpload({ done, total }));
    setUpload(null);
    setResult(out);
    onUploaded();
  }

  async function runExport(format: "csv" | "xlsx" | "pdf") {
    setBusy(format);
    setError(null);
    try {
      const { url, filename } = await exportAssessment(a.id, format);
      const link = document.createElement("a");
      link.href = exportUrl(url);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      closeMenu(exportMenu.current);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function togglePause() {
    closeMenu(moreMenu.current);
    setBusy("pause");
    try {
      onChange(await (a.paused ? resumeAssessment(a.id) : pauseAssessment(a.id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    closeMenu(moreMenu.current);
    if (!window.confirm(t.asm.confirmDelete(a.title))) return;
    setBusy("delete");
    try {
      await deleteAssessment(a.id);
      router.push("/assessments");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  }

  const meta = [a.course, t.asm.papersCount(a.papers.length), t.asm.outOf(a.scale), t.langName[a.language]].filter(Boolean).join(" · ");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-3xl">
          {editing ? (
            <input
              autoFocus
              defaultValue={a.title}
              aria-label={t.asm.titleLabel}
              className="field font-serif text-3xl leading-tight font-semibold sm:text-4xl"
              onBlur={(e) => void rename(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
                if (e.key === "Escape") setEditing(false);
              }}
            />
          ) : (
            <h1>
              <button
                type="button"
                onClick={() => setEditing(true)}
                title={t.asm.rename}
                className="-mx-1 rounded-md px-1 text-left font-serif text-3xl leading-tight font-semibold tracking-tight break-words hover:bg-sunken sm:text-4xl"
              >
                {a.title}
              </button>
            </h1>
          )}
          <p className="mt-1.5 text-muted">{meta}</p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <label className={`btn btn-secondary cursor-pointer ${upload ? "pointer-events-none opacity-60" : ""}`}>
            <Icon name="upload" size={16} />
            {upload ? t.asm.addingPapers(upload.done, upload.total) : t.asm.addPapers}
            <input
              type="file"
              multiple
              accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png"
              className="sr-only"
              disabled={!!upload}
              onChange={(e) => {
                const picked = mergeFiles([], Array.from(e.currentTarget.files ?? []));
                e.currentTarget.value = "";
                void addPapers(picked);
              }}
            />
          </label>
          <details ref={exportMenu} className="group relative">
            <summary className="btn btn-primary cursor-pointer list-none [&::-webkit-details-marker]:hidden" aria-busy={busy === "csv" || busy === "xlsx" || busy === "pdf"}>
              <Icon name="export" size={16} />
              {busy === "csv" || busy === "xlsx" || busy === "pdf" ? t.preparingExport : t.asm.exportLabel}
              <Icon name="chevron" size={14} className="transition-transform group-open:rotate-180" />
            </summary>
            <div className="absolute top-full right-0 z-20 mt-2 w-80 rounded-lg border border-rule bg-surface p-1.5 shadow-lg">
              {(["xlsx", "csv", "pdf"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void runExport(f)}
                  className="flex w-full items-start gap-3 rounded-md px-2.5 py-2 text-left hover:bg-sunken disabled:opacity-50"
                >
                  <Icon name="file" size={18} className="mt-0.5 shrink-0 text-accent" />
                  <span>
                    <span className="block text-sm font-semibold">{{ xlsx: t.asm.exportXlsx, csv: t.asm.exportCsv, pdf: t.asm.exportPdf }[f]}</span>
                    <span className="block text-xs text-muted">{{ xlsx: t.asm.exportXlsxHint, csv: t.asm.exportCsvHint, pdf: t.asm.exportPdfHint }[f]}</span>
                  </span>
                </button>
              ))}
            </div>
          </details>
          <details ref={moreMenu} className="relative">
            <summary className="btn-icon cursor-pointer list-none [&::-webkit-details-marker]:hidden" aria-label={t.asm.actions} title={t.asm.actions}>
              <Icon name="more" />
            </summary>
            <div className="absolute top-full right-0 z-20 mt-2 w-64 rounded-lg border border-rule bg-surface p-1.5 shadow-lg">
              <button type="button" onClick={() => void togglePause()} disabled={busy !== null} className="flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-sm hover:bg-sunken">
                <Icon name={a.paused ? "play" : "pause"} size={16} className="text-muted" />
                {a.paused ? t.asm.resume : t.asm.pause}
              </button>
              <button type="button" onClick={() => void remove()} disabled={busy !== null} className="flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-sm text-danger-ink hover:bg-rec-soft">
                <Icon name="trash" size={16} />
                {t.asm.deleteAssessment}
              </button>
            </div>
          </details>
        </div>
      </div>
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      {result && (result.added > 0 || result.skipped.length > 0 || result.error) && (
        <div className={`notice ${result.skipped.length || result.error ? "notice-warn" : "notice-info"}`} role="status">
          <div className="min-w-0 flex-1 space-y-1">
            {result.added > 0 && <p>{t.asm.papersAdded(result.added)}</p>}
            {result.error && <p>{result.error}</p>}
            {result.skipped.length > 0 && (
              <>
                <p className="font-semibold">{t.asm.skippedTitle}</p>
                <ul className="space-y-0.5">
                  {result.skipped.map((s, i) => (
                    <li key={`${s.filename}-${i}`}>
                      {s.filename} — {s.reason}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
          <button type="button" className="btn-icon -my-1" aria-label={t.close} onClick={() => setResult(null)}>
            <Icon name="close" size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
