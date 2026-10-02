"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { DeckTile } from "@/components/deck/DeckTile";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { deleteDeck } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { DeckSummary } from "@/lib/types";
import { useLibrary } from "@/lib/useLibrary";

export default function SlidesList() {
  const { t } = useI18n();
  const { decks, error, setLib } = useLibrary(["decks"]);
  const [actionError, setActionError] = useState<string | null>(null);
  const deleting = useRef(new Set<string>());

  async function onDelete(d: DeckSummary) {
    if (deleting.current.has(d.id) || !window.confirm(t.confirmDeleteDeck(d.title, d.animation_count))) return;
    deleting.current.add(d.id);
    setActionError(null);
    try {
      await deleteDeck(d.id);
      setLib((l) => ({ ...l, decks: l.decks?.filter((x) => x.id !== d.id) ?? null }));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      deleting.current.delete(d.id);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageHeader title={t.nav.slides} subtitle={t.slidesSubtitle}>
        <Link href="/new/slides" className="btn btn-primary">
          <Icon name="plus" size={16} />
          {t.newSlides}
        </Link>
      </PageHeader>
      {(error || actionError) && (
        <p className="notice notice-error" role="alert">
          {error ? t.loadError(error) : actionError}
        </p>
      )}
      {!decks && !error && (
        <p className="text-muted" aria-live="polite">
          {t.loading}
        </p>
      )}
      {decks?.length === 0 && <p className="text-muted">{t.noDecks}</p>}
      {decks && decks.length > 0 && (
        <ul className="grid grid-cols-1 gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {decks.map((d) => (
            <DeckTile key={d.id} d={d} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </div>
  );
}
