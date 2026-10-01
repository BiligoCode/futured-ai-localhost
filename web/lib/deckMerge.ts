import type { ChatResult, EditLog, Slide } from "./types";

/** Insert `slide` into `list` right after the slide that precedes it in `order` and still exists in `list`;
 * at the start when none does. */
function placeAfterPredecessor(list: Slide[], slide: Slide, order: string[]): Slide[] {
  const at = order.indexOf(slide.id);
  for (let i = at - 1; i >= 0; i--) {
    const j = list.findIndex((x) => x.id === order[i]);
    if (j >= 0) return [...list.slice(0, j + 1), slide, ...list.slice(j + 1)];
  }
  return [slide, ...list];
}

/** Merge the assistant's result into the professor's local slides.
 *
 * `baseline` is the slide order the server had when the request was sent (after the flush). The server's list
 * carries the AI's inserts, deletes and moves; on top of it we keep what the professor did while waiting: text
 * typed in slides the AI did not touch, slides they added (placed after their local predecessor) and slides they
 * deleted (unless the AI edited that very slide — then the AI's edit wins). Videos only change on the server. */
export function mergeChatResult(local: Slide[], result: ChatResult, baseline: string[]): Slide[] {
  const edited = new Set(result.edits.map((e) => e.slide_id));
  const mine = new Map(local.map((s) => [s.id, s]));
  const localIds = new Set(local.map((s) => s.id));
  const base = new Set(baseline);

  let merged: Slide[] = result.deck.slides
    .filter((server) => localIds.has(server.id) || !base.has(server.id) || edited.has(server.id))
    .map((server) => {
      const ours = mine.get(server.id);
      return { id: server.id, html: ours && !edited.has(server.id) ? ours.html : server.html, video: server.video };
    });

  const localOrder = local.map((s) => s.id);
  for (const slide of local) {
    if (!base.has(slide.id) && !merged.some((m) => m.id === slide.id)) merged = placeAfterPredecessor(merged, slide, localOrder);
  }
  return merged;
}

/** Undo exactly what the assistant did, leaving the professor's later work alone: replaced slides get their old
 * HTML back, inserted slides go, deleted slides return where they were, moved slides go back after their old
 * neighbour. Slides that no longer exist are skipped. */
export function undoChatEdits(current: Slide[], snapshot: Slide[], edits: EditLog[]): Slide[] {
  const old = new Map(snapshot.map((s) => [s.id, s]));
  const order = snapshot.map((s) => s.id);
  let slides = [...current];
  for (const e of [...edits].reverse()) {
    const was = old.get(e.slide_id);
    const i = slides.findIndex((s) => s.id === e.slide_id);
    if (e.op === "replace" && was && i >= 0) slides[i] = { ...slides[i], html: was.html };
    else if (e.op === "insert_after" && i >= 0) slides.splice(i, 1);
    else if (e.op === "delete" && was && i < 0) slides = placeAfterPredecessor(slides, was, order);
    else if (e.op === "move" && i >= 0) {
      const [moved] = slides.splice(i, 1);
      slides = placeAfterPredecessor(slides, moved, order);
    }
  }
  return slides;
}
