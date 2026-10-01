import { expect, test } from "vitest";

import { DEFAULT_RATIO, clampRatio, readRatio } from "./useDeckSplit";

test("clampRatio keeps the editor between 30 % and 75 % of the width", () => {
  expect(clampRatio(0.1)).toBe(0.3);
  expect(clampRatio(0.9)).toBe(0.75);
  expect(clampRatio(0.5)).toBe(0.5);
});

test("readRatio falls back to the default for missing or bad values", () => {
  expect(DEFAULT_RATIO).toBe(0.6);
  expect(readRatio(null)).toBe(0.6);
  expect(readRatio("abc")).toBe(0.6);
  expect(readRatio("0.5")).toBe(0.5);
  expect(readRatio("2")).toBe(0.75);
});
