import type { ChatResult, Slide } from "./types";

/** Merge the assistant's result into the professor's local slides.
 *
 * The server's list defines order and membership (inserts, deletions, moves); a slide the assistant did not
 * touch keeps the local HTML, because the professor may have typed in it while the model was thinking. Videos
 * are only ever changed on the server, so they always come from there. */
export function mergeChatResult(local: Slide[], result: ChatResult): Slide[] {
  const edited = new Set(result.edits.map((e) => e.slide_id));
  const mine = new Map(local.map((s) => [s.id, s]));
  return result.deck.slides.map((server) => {
    const ours = mine.get(server.id);
    const html = ours && !edited.has(server.id) ? ours.html : server.html;
    return { id: server.id, html, video: server.video };
  });
}
