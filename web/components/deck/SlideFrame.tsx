"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { SLIDE_W } from "@/lib/slideHtml";

/** A 1280×720 slide zoomed to the width it is given. `children` is the slide text; `video` renders under it. */
export function SlideFrame({ children, video, footerLeft, footerRight, className, textRef, overflow, onClick }: {
  children: React.ReactNode;
  video?: React.ReactNode;
  footerLeft?: string;
  footerRight?: string;
  className?: string;
  textRef?: React.Ref<HTMLDivElement>;
  overflow?: boolean;
  onClick?: () => void;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const measure = () => setZoom(el.clientWidth / SLIDE_W);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={wrap} className={`slide-frame ${className ?? ""}`} onClick={onClick}>
      <div
        className={`slide ${overflow ? "slide-overflow" : ""}`}
        style={{ zoom: zoom ?? 1, visibility: zoom === null ? "hidden" : undefined }}
      >
        <div ref={textRef} className="slide-text">
          {children}
        </div>
        {video}
        {(footerLeft || footerRight) && (
          <footer className="slide-footer" aria-hidden="true">
            <span>{footerLeft}</span>
            <span>{footerRight}</span>
          </footer>
        )}
      </div>
    </div>
  );
}
