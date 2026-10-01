"use client";

import { useRef } from "react";

/** Video that shows a frame from inside the clip (Manim scenes start on an empty frame) until played. */
export function ScenePreview({ src, className, muted }: { src: string; className?: string; muted?: boolean }) {
  const started = useRef(false);
  return (
    <video
      src={src}
      controls
      muted={muted}
      preload="metadata"
      className={className}
      onLoadedMetadata={(e) => {
        const v = e.currentTarget;
        if (!started.current && Number.isFinite(v.duration)) v.currentTime = v.duration * 0.7;
      }}
      onPlay={(e) => {
        if (!started.current) {
          started.current = true;
          e.currentTarget.currentTime = 0;
        }
      }}
    />
  );
}
