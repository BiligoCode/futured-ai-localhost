"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { embedAnimation, getDeck } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { slideTitle } from "@/lib/slideHtml";
import type { Deck, EmbedMode, Project } from "@/lib/types";

import { SlideThumb } from "./SlideThumb";

/** "Add to slides": pick where a finished animation goes in its deck. */
export function EmbedDialog({ project, deckId, onClose }: { project: Project; deckId: string; onClose: () => void }) {
  const { t } = useI18n();
  const router = useRouter();
  const [deck, setDeck] = useState<Deck | null>(null);
  const [slideId, setSlideId] = useState<string | null>(null);
  const [mode, setMode] = useState<EmbedMode>("append");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    getDeck(deckId)
      .then((d) => {
        if (cancelled) return;
        setDeck(d);
        setSlideId(d.slides[d.slides.length - 1]?.id ?? null);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [deckId]);

  useEffect(() => {
    const el = dialog.current;
    el?.querySelector<HTMLElement>("input, button")?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && el) {
        const focusable = Array.from(el.querySelectorAll<HTMLElement>("input, button, [tabindex]:not([tabindex='-1'])")).filter((f) => !f.hasAttribute("disabled"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const updated = await embedAnimation(deckId, { project_id: project.id, slide_id: mode === "new_end" ? null : slideId, mode });
      const target = mode === "append" ? slideId : [...updated.slides].reverse().find((s) => s.video === project.id)?.id;
      router.push(`/decks/${deckId}${target ? `#slide-${target}` : ""}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const chosen = deck?.slides.find((s) => s.id === slideId);
  const needsSlide = mode !== "new_end";
  const modes: { value: EmbedMode; label: string }[] = [
    { value: "append", label: t.embedAppend },
    { value: "new_after", label: t.embedNewAfter },
    { value: "new_end", label: t.embedNewEnd },
  ];

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-stage/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="embed-title"
        onClick={(e) => e.stopPropagation()}
        className="panel flex max-h-[90dvh] w-full max-w-2xl flex-col overflow-hidden shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-rule px-6 py-4">
          <div>
            <h2 id="embed-title" className="font-serif text-2xl font-semibold">
              {t.embedTitle}
            </h2>
            <p className="mt-0.5 text-sm text-muted">{deck ? deck.title : t.loading}</p>
          </div>
          <button type="button" onClick={onClose} className="btn-icon" aria-label={t.close}>
            <Icon name="close" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {deck && (
            <fieldset disabled={busy}>
              <legend className="sr-only">{t.slidesLabel}</legend>
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {deck.slides.map((s, i) => (
                  <li key={s.id}>
                    <label className={`block cursor-pointer rounded-lg ring-2 transition-[box-shadow] ${slideId === s.id && needsSlide ? "ring-accent" : "ring-transparent hover:ring-rule-strong"} ${!needsSlide ? "opacity-50" : ""}`}>
                      <input type="radio" name="slide" value={s.id} checked={slideId === s.id} onChange={() => setSlideId(s.id)} className="sr-only" disabled={!needsSlide} />
                      <SlideThumb html={s.html} video={!!s.video} className="pointer-events-none ring-1 ring-rule" />
                      <span className="mt-1 block truncate px-1 text-xs text-muted">
                        {i + 1}. {slideTitle(s.html) || t.slideN(i + 1)}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          )}
          {error && (
            <p className="notice notice-error mt-4" role="alert">
              {error}
            </p>
          )}
        </div>

        <div className="space-y-3 border-t border-rule bg-paper/60 px-6 py-4">
          <div className="grid auto-cols-fr grid-flow-col gap-1 rounded-lg bg-sunken p-1" role="radiogroup" aria-label={t.embedTitle}>
            {modes.map((m) => (
              <label key={m.value} className="cursor-pointer">
                <input type="radio" name="mode" value={m.value} checked={mode === m.value} onChange={() => setMode(m.value)} className="peer sr-only" />
                <span className="block rounded-md px-3 py-2 text-center text-sm text-muted transition-colors peer-checked:bg-surface peer-checked:font-semibold peer-checked:text-ink peer-checked:shadow-[0_1px_2px_rgb(15_20_27/0.12)] peer-focus-visible:outline-2 peer-focus-visible:outline-accent hover:text-ink">
                  {m.label}
                </span>
              </label>
            ))}
          </div>
          {mode === "append" && chosen?.video && <p className="notice notice-warn">{t.embedReplaces}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="btn btn-ghost">
              {t.cancel}
            </button>
            <button type="button" onClick={() => void confirm()} disabled={busy || !deck || (needsSlide && !slideId)} className="btn btn-primary">
              {busy ? t.adding : t.embedConfirm}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
