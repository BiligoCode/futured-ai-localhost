"use client";

import Link from "next/link";

import { Icon } from "@/components/Icon";
import { CurveSketch } from "@/components/Stage";
import { useI18n } from "@/lib/i18n";

/** A small 16:9 slide with text bars and an embedded clip: the Slides card's emblem. */
function SlideSketch({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 160 90" className={className} aria-hidden="true" fill="none">
      <rect x="1" y="1" width="158" height="88" rx="6" className="fill-surface stroke-rule-strong" strokeWidth="1.5" />
      <rect x="16" y="16" width="70" height="7" rx="2" className="fill-ink" />
      <rect x="16" y="32" width="96" height="4" rx="2" className="fill-faint" />
      <rect x="16" y="42" width="84" height="4" rx="2" className="fill-faint" />
      <rect x="16" y="52" width="90" height="4" rx="2" className="fill-faint" />
      <rect x="100" y="56" width="44" height="26" rx="3" className="fill-stage" />
      <path d="M118 63.5v11l9-5.5-9-5.5Z" className="fill-manim" />
    </svg>
  );
}

export default function Chooser() {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="max-w-2xl">
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight">{t.chooseTitle}</h1>
        <p className="mt-2 text-lg text-muted">{t.chooseSubtitle}</p>
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <Link
          href="/new/animation"
          className="group stage stage-grid flex min-h-[20rem] flex-col justify-end rounded-2xl p-7 ring-1 ring-black/5 transition-[box-shadow] hover:shadow-[0_18px_40px_-18px_rgb(15_20_27/0.6)] focus-visible:outline-offset-4"
        >
          <CurveSketch className="pointer-events-none absolute top-6 right-6 w-1/2 opacity-90" />
          <h2 className="font-serif text-3xl leading-tight font-semibold">{t.chooseAnimation}</h2>
          <p className="mt-2 max-w-sm text-sm text-stage-muted">{t.chooseAnimationBody}</p>
          <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-manim">
            {t.chooseStart}
            <Icon name="send" size={16} className="transition-transform group-hover:translate-x-0.5" />
          </span>
        </Link>

        <Link
          href="/new/slides"
          className="group panel relative flex min-h-[20rem] flex-col justify-end overflow-hidden p-7 transition-[box-shadow,border-color] hover:border-accent hover:shadow-[0_18px_40px_-18px_rgb(15_20_27/0.35)] focus-visible:outline-offset-4"
        >
          <SlideSketch className="pointer-events-none absolute top-6 right-6 w-1/2 drop-shadow-[0_6px_14px_rgb(15_20_27/0.12)]" />
          <h2 className="font-serif text-3xl leading-tight font-semibold">{t.chooseSlides}</h2>
          <p className="mt-2 max-w-sm text-sm text-muted">{t.chooseSlidesBody}</p>
          <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-accent">
            {t.chooseStart}
            <Icon name="send" size={16} className="transition-transform group-hover:translate-x-0.5" />
          </span>
        </Link>
      </div>
    </div>
  );
}
