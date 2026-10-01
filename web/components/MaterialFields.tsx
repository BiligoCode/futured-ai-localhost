"use client";

import { useI18n } from "@/lib/i18n";

import { Icon } from "./Icon";

/** Course material inputs shared by the animation and the slides setup: PDFs (`files`) and pasted text
 * (`material_text`). `children` renders above the picker, for material that is already attached. */
export function MaterialFields({ files, onFiles, defaultText, children }: {
  files: File[];
  onFiles: (files: File[]) => void;
  defaultText?: string;
  children?: React.ReactNode;
}) {
  const { t } = useI18n();

  function addFiles(input: HTMLInputElement) {
    const picked = Array.from(input.files ?? []);
    // Reset so picking the same file again after removing it still fires onChange.
    input.value = "";
    onFiles([...files, ...picked.filter((f) => !files.some((p) => p.name === f.name && p.size === f.size))]);
  }

  return (
    <>
      <div>
        <span className="label">{t.notesLabel}</span>
        {children}
        <label className="group flex cursor-pointer items-center gap-4 rounded-lg border border-dashed border-rule-strong bg-paper px-4 py-4 transition-colors hover:border-accent focus-within:border-accent focus-within:outline-2 focus-within:outline-accent">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-surface text-accent ring-1 ring-rule">
            <Icon name="file" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink">{files.length ? t.addMorePdfs : t.choosePdfs}</span>
            <span className="hint block">{t.pdfHint}</span>
          </span>
          <input name="files" type="file" accept="application/pdf" multiple className="sr-only" onChange={(e) => addFiles(e.currentTarget)} />
        </label>
        {files.length > 0 && (
          <ul className="mt-2 space-y-1">
            {files.map((f, i) => (
              <li key={`${f.name}-${f.size}`} className="flex items-center gap-2 rounded-md bg-sunken px-3 py-1.5 text-sm">
                <Icon name="file" size={16} className="shrink-0 text-accent" />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <button
                  type="button"
                  aria-label={t.removeFile(f.name)}
                  className="text-muted hover:text-ink"
                  onClick={() => onFiles(files.filter((_, j) => j !== i))}
                >
                  <Icon name="close" size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <label htmlFor="material_text" className="label">
          {t.pasteLabel}
        </label>
        <textarea
          id="material_text"
          name="material_text"
          rows={6}
          autoComplete="off"
          defaultValue={defaultText}
          className="field"
          placeholder={t.pastePlaceholder}
        />
        <p className="hint mt-1.5">{t.noMaterialHint}</p>
      </div>
    </>
  );
}
