import type { Cut } from "./types";

export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** "0:32–0:50": where a scene sits in a composed video, or null if it is not in it. */
export function rangeOf(cut: Cut, sceneId: string): string | null {
  const seg = cut.segments.find((s) => s.scene_id === sceneId);
  return seg ? `${clock(seg.start)}–${clock(seg.end)}` : null;
}
