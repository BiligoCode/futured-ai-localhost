import { describe, expect, test } from "vitest";

import { mergeChatResult } from "./deckMerge";
import type { ChatResult, Deck, Slide } from "./types";

const s = (id: string, html: string, video: string | null = null): Slide => ({ id, html, video });

function result(slides: Slide[], edits: ChatResult["edits"]): ChatResult {
  const deck = { id: "d", slides, version: 7, animations: [], chat: [] } as unknown as Deck;
  return { deck, reply: "ok", edits };
}

describe("mergeChatResult", () => {
  test("keeps local html of untouched slides and takes server html for edited ones", () => {
    const local = [s("a", "<p>A local</p>"), s("b", "<p>B typed while waiting</p>")];
    const r = result([s("a", "<p>A from the model</p>"), s("b", "<p>B stale</p>")], [{ op: "replace", slide_id: "a", title: "A" }]);
    expect(mergeChatResult(local, r)).toEqual([s("a", "<p>A from the model</p>"), s("b", "<p>B typed while waiting</p>")]);
  });

  test("follows server order and membership", () => {
    const local = [s("a", "<p>a</p>"), s("b", "<p>b local</p>"), s("c", "<p>c</p>")];
    const r = result([s("a", "<p>a</p>"), s("d", "<p>d new</p>"), s("b", "<p>b</p>")], [
      { op: "delete", slide_id: "c", title: "c" },
      { op: "insert_after", slide_id: "d", title: "d new" },
    ]);
    expect(mergeChatResult(local, r)).toEqual([s("a", "<p>a</p>"), s("d", "<p>d new</p>"), s("b", "<p>b local</p>")]);
  });

  test("video always comes from the server", () => {
    const local = [s("a", "<p>a</p>", "old")];
    const r = result([s("a", "<p>a</p>", "new")], []);
    expect(mergeChatResult(local, r)[0].video).toBe("new");
  });
});
