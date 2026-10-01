"use client";

import { Icon } from "@/components/Icon";
import { cutUrl, posterUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AnimationRef } from "@/lib/types";

/** The animation embedded in a slide, shown under its text. Not part of the slide HTML, so the AI never touches it. */
export function VideoBlock({ animation, deckId, onRemove }: {
  animation: AnimationRef | undefined;
  deckId: string;
  onRemove: () => void;
}) {
  const { t } = useI18n();
  const missing = !animation || animation.status === "missing";
  const remove = (
    <button
      type="button"
      onClick={onRemove}
      aria-label={t.removeFromSlide}
      title={t.removeFromSlide}
      className="absolute top-3 right-3 grid h-11 w-11 place-items-center rounded-full bg-black/60 text-white hover:bg-black/85"
    >
      <Icon name="close" size={22} />
    </button>
  );
  if (missing || !animation.cut) {
    return (
      <figure className="slide-video" contentEditable={false}>
        <div className="relative mx-auto grid h-[300px] w-[533px] place-items-center rounded-lg bg-sunken text-muted">
          <span className="flex items-center gap-3 text-[22px]">
            <Icon name="film" size={28} />
            {missing ? t.animationDeleted : t.animationNotReady}
          </span>
          {remove}
        </div>
      </figure>
    );
  }
  return (
    <figure className="slide-video" contentEditable={false}>
      <div className="relative mx-auto w-fit">
        <video
          controls
          preload="metadata"
          playsInline
          poster={posterUrl(deckId, animation.project_id)}
          src={cutUrl(animation.project_id, animation.cut, animation.version)}
        />
        {remove}
      </div>
      <figcaption>{t.animationCaption(animation.title)}</figcaption>
    </figure>
  );
}
