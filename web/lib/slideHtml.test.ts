import { describe, expect, test } from "vitest";

import { PALETTE, SIZES, SLIDE_H, SLIDE_W, slideText, slideTitle } from "./slideHtml";

describe("slideTitle", () => {
  test("uses the first heading and decodes entities", () => {
    expect(slideTitle('<h1 style="text-align: center">Α &amp; Β</h1><p>x</p>')).toBe("Α & Β");
    expect(slideTitle("<p>intro</p><h2>Δεύτερο &lt;3</h2>")).toBe("Δεύτερο <3");
  });
  test("falls back to the first 60 characters of text", () => {
    expect(slideTitle("<p>" + "λ".repeat(80) + "</p>")).toBe("λ".repeat(60));
    expect(slideTitle("<p>ένα</p><p>δύο</p>")).toBe("ένα δύο");
  });
  test("is empty for an empty slide", () => {
    expect(slideTitle("")).toBe("");
    expect(slideTitle("<p></p>")).toBe("");
  });
});

describe("slideText", () => {
  test("one line per block, dashes for list items", () => {
    expect(slideText("<h1>Τ</h1><ul><li><p>ένα</p></li><li>δύο</li></ul>")).toBe("Τ\n- ένα\n- δύο");
    expect(slideText("<p>a<br>b</p>")).toBe("a\nb");
  });
});

test("constants match the slide contract", () => {
  expect([SLIDE_W, SLIDE_H]).toEqual([1280, 720]);
  expect(PALETTE.map((c) => c.hex)).toEqual(["#18212e", "#566173", "#1b6f8c", "#0f7b6c", "#74490a", "#c93838", "#6d3fb8", "#e2a13b"]);
  expect(SIZES.map((s) => s.px)).toEqual([20, 26, 34, 44]);
});
