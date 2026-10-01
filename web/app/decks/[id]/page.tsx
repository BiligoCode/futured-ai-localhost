"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { DeckWorkspace } from "@/components/deck/DeckWorkspace";
import { getDeck } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Deck } from "@/lib/types";

export default function DeckPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const [deck, setDeck] = useState<Deck | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDeck(id)
      .then((d) => !cancelled && setDeck(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error)
    return (
      <p className="notice notice-error mx-auto max-w-6xl" role="alert">
        {error}
      </p>
    );
  if (!deck)
    return (
      <p className="mx-auto max-w-6xl text-muted" aria-live="polite">
        {t.loading}
      </p>
    );
  return <DeckWorkspace key={deck.id} deck={deck} />;
}
