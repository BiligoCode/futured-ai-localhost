"use client";

import { Icon } from "@/components/Icon";

import { SlideFrame } from "./SlideFrame";

/** A read-only, scaled-down slide (strip, dashboard, embed dialog). The HTML is server-sanitised. */
export function SlideThumb({ html, video, footerLeft, footerRight, className }: {
  html: string;
  video?: boolean;
  footerLeft?: string;
  footerRight?: string;
  className?: string;
}) {
  return (
    <SlideFrame
      className={className}
      footerLeft={footerLeft}
      footerRight={footerRight}
      video={
        video ? (
          <figure className="slide-video">
            <div className="mx-auto grid h-[300px] w-[533px] place-items-center rounded-lg bg-stage text-stage-muted">
              <Icon name="film" size={96} />
            </div>
          </figure>
        ) : undefined
      }
    >
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </SlideFrame>
  );
}
