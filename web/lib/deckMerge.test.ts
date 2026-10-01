import { describe, expect, test } from "vitest";

import { mergeChatResult, undoChatEdits } from "./deckMerge";
import type { ChatResult, Deck, EditLog, Slide } from "./types";

const s = (id: string, html: string, video: string | null = null): Slide => ({ id, html, video });

function result(slides: Slide[], edits: EditLog[]): ChatResult {
  const deck = { id: "d", slides, version: 7, animations: [], chat: [] } as unknown as Deck;
  return { deck, reply: "ok", edits };
}

describe("mergeChatResult", () => {
  const baseline = ["a", "b", "c"];

  test("keeps local html of untouched slides and takes server html for edited ones", () => {
    const local = [s("a", "<p>A local</p>"), s("b", "<p>B typed while waiting</p>"), s("c", "<p>c</p>")];
    const r = result([s("a", "<p>A from the model</p>"), s("b", "<p>B stale</p>"), s("c", "<p>c</p>")], [{ op: "replace", slide_id: "a", title: "A" }]);
    expect(mergeChatResult(local, r, baseline)).toEqual([s("a", "<p>A from the model</p>"), s("b", "<p>B typed while waiting</p>"), s("c", "<p>c</p>")]);
  });

  test("follows the server's order and the AI's inserts and deletes", () => {
    const local = [s("a", "<p>a</p>"), s("b", "<p>b local</p>"), s("c", "<p>c</p>")];
    const r = result([s("a", "<p>a</p>"), s("d", "<p>d new</p>"), s("b", "<p>b</p>")], [
      { op: "delete", slide_id: "c", title: "c" },
      { op: "insert_after", slide_id: "d", title: "d new" },
    ]);
    expect(mergeChatResult(local, r, baseline)).toEqual([s("a", "<p>a</p>"), s("d", "<p>d new</p>"), s("b", "<p>b local</p>")]);
  });

  test("video always comes from the server", () => {
    const local = [s("a", "<p>a</p>", "old")];
    expect(mergeChatResult(local, result([s("a", "<p>a</p>", "new")], []), ["a"])[0].video).toBe("new");
  });

  test("keeps a slide the professor added while waiting, after its local predecessor", () => {
    const local = [s("a", "<p>a</p>"), s("x", "<p>typed while waiting</p>"), s("b", "<p>b</p>"), s("c", "<p>c</p>")];
    const r = result([s("a", "<p>a</p>"), s("b", "<p>B model</p>"), s("c", "<p>c</p>")], [{ op: "replace", slide_id: "b", title: "B" }]);
    expect(mergeChatResult(local, r, baseline).map((sl) => sl.id)).toEqual(["a", "x", "b", "c"]);
    expect(mergeChatResult(local, r, baseline)[1].html).toBe("<p>typed while waiting</p>");
  });

  test("keeps a local deletion unless the AI edited that slide", () => {
    const local = [s("a", "<p>a</p>"), s("c", "<p>c</p>")]; // b deleted while waiting
    const untouched = result([s("a", "<p>a</p>"), s("b", "<p>b</p>"), s("c", "<p>c</p>")], []);
    expect(mergeChatResult(local, untouched, baseline).map((sl) => sl.id)).toEqual(["a", "c"]);
    const edited = result([s("a", "<p>a</p>"), s("b", "<p>B model</p>"), s("c", "<p>c</p>")], [{ op: "replace", slide_id: "b", title: "B" }]);
    expect(mergeChatResult(local, edited, baseline).map((sl) => sl.id)).toEqual(["a", "b", "c"]);
  });
});

describe("undoChatEdits", () => {
  const snapshot = [s("a", "<p>a old</p>"), s("b", "<p>b</p>"), s("c", "<p>c</p>")];

  test("restores only the slides the AI replaced, keeping later local edits elsewhere", () => {
    const current = [s("a", "<p>a from model</p>"), s("b", "<p>b edited later</p>"), s("c", "<p>c</p>")];
    expect(undoChatEdits(current, snapshot, [{ op: "replace", slide_id: "a", title: "" }])).toEqual([
      s("a", "<p>a old</p>"), s("b", "<p>b edited later</p>"), s("c", "<p>c</p>"),
    ]);
  });

  test("removes slides the AI inserted and brings back slides it deleted, in place", () => {
    const current = [s("a", "<p>a</p>"), s("n", "<p>new</p>"), s("c", "<p>c</p>")]; // AI inserted n after a, deleted b
    const edits: EditLog[] = [{ op: "insert_after", slide_id: "n", title: "" }, { op: "delete", slide_id: "b", title: "" }];
    expect(undoChatEdits(current, snapshot, edits).map((sl) => sl.id)).toEqual(["a", "b", "c"]);
  });

  test("puts a moved slide back after its old predecessor and leaves everything else alone", () => {
    const current = [s("c", "<p>c</p>"), s("a", "<p>a old</p>"), s("b", "<p>b</p>"), s("z", "<p>added later</p>")];
    expect(undoChatEdits(current, snapshot, [{ op: "move", slide_id: "c", title: "" }]).map((sl) => sl.id)).toEqual(["a", "b", "c", "z"]);
  });

  test("ignores slides that no longer exist and keeps a replaced slide's current video", () => {
    const current = [s("a", "<p>a from model</p>", "vid")];
    expect(undoChatEdits(current, snapshot, [{ op: "replace", slide_id: "a", title: "" }, { op: "replace", slide_id: "gone", title: "" }])).toEqual([
      s("a", "<p>a old</p>", "vid"),
    ]);
  });
});
