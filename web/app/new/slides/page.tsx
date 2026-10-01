"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { MaterialFields } from "@/components/MaterialFields";
import { LANGUAGES, Segmented } from "@/components/Segmented";
import { createDeck } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function NewDeck() {
  const { lang, t } = useI18n();
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    form.delete("files");
    for (const f of files) form.append("files", f);
    try {
      const deck = await createDeck(form);
      router.push(`/decks/${deck.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="max-w-2xl">
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight">{t.deckNewTitle}</h1>
        <p className="mt-2 text-lg text-muted">{t.deckNewSubtitle}</p>
      </div>

      <form onSubmit={onSubmit} className="panel grid overflow-hidden lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="space-y-6 p-6 sm:p-8">
          <div>
            <label htmlFor="title" className="label">
              {t.deckTitleLabel}
            </label>
            <input
              id="title"
              name="title"
              required
              autoComplete="off"
              className="field font-serif text-2xl leading-snug"
              placeholder={t.deckTitlePlaceholder}
            />
          </div>
          <MaterialFields files={files} onFiles={setFiles} />
        </div>

        <div className="flex flex-col gap-6 border-t border-rule bg-paper/60 p-6 sm:p-8 lg:border-t-0 lg:border-l">
          <Segmented name="language" legend={t.deckLanguage} hint={t.deckLanguageHint} options={LANGUAGES} defaultValue={lang} />
          <div className="mt-auto space-y-3 pt-2">
            {error && (
              <p className="notice notice-error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" disabled={submitting} className="btn btn-primary w-full py-3 disabled:cursor-wait">
              {submitting ? t.creatingDeck : t.createDeck}
            </button>
            <p className="hint text-center">{t.deckStartHint}</p>
          </div>
        </div>
      </form>
    </div>
  );
}
