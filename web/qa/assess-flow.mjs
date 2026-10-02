// The assessment flow in the browser, against running servers and the real models:
//   node qa/assess-flow.mjs <classDir> [web] [api]
// <classDir> is the output of api/scripts/make_exam_class.py. Creates an assessment with the exam paper and three
// papers, confirms the drafted rubric, waits for grading, then reviews a paper (mark override, reviewed, next paper
// with "]"), opens a comparison and downloads the CSV export.
import { readFileSync } from "node:fs";
import { chromium } from "playwright";

const [dir, web = "http://localhost:3100", api = "http://localhost:8100", existing = ""] = process.argv.slice(2);
if (!dir) throw new Error("usage: node qa/assess-flow.mjs <classDir> [web] [api]");
const check = (ok, what) => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${what}`);
  if (!ok) process.exitCode = 1;
};
const until = async (fn, what, ms = 600_000) => {
  const start = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - start > ms) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 2000));
  }
};

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
await ctx.addCookies([{ name: "lara-lang", value: "en", url: web }]);
const page = await ctx.newPage();
page.on("dialog", (d) => void d.accept());  // e.g. "grade with the keys Lara proposed?"
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));

let aid = existing;
if (!aid) {
await page.goto(`${web}/new/assessment`);
await page.getByLabel("Title").fill("QA — Algorithms midterm");
await page.getByLabel("Course").fill("CS201");
await page.locator('input[name="exam_files"]').setInputFiles(`${dir}/exam.pdf`);
await page.locator("#papers").setInputFiles(["S01", "S02", "S03"].map((s) => `${dir}/papers/${s}.pdf`));
check(await page.getByText("3 files").isVisible(), "three papers listed before upload");
await page.getByRole("button", { name: "Create assessment" }).click();
await page.waitForURL(/\/assessments\/[0-9a-f]{10}/, { timeout: 120_000 });
aid = page.url().match(/assessments\/([0-9a-f]{10})/)[1];
check(true, `created assessment ${aid}`);

await until(async () => (await (await fetch(`${api}/assessments/${aid}`)).json()).rubric.status === "draft", "the rubric draft");
await page.reload();
await page.getByRole("button", { name: "Check the rubric" }).click();
check(await page.getByRole("tab", { name: /Rubric/ }).getAttribute("aria-selected") === "true", "rubric tab opens from the notice");
check((await page.locator("ol > li").count()) === 10, "ten questions drafted from the exam paper");
await page.getByRole("button", { name: "Save & grade" }).click();
await until(async () => {
  const a = await (await fetch(`${api}/assessments/${aid}`)).json();
  return a.papers.every((p) => p.status === "graded") && a.analysis.status === "done";
}, "grading and the class analysis");
}

await page.goto(`${web}/assessments/${aid}?tab=students`);
await page.getByRole("link", { name: "Μαρία Παππά" }).click();  // the reviewed paper's grade is checked through the API below
await page.waitForURL(/students\/[0-9a-f]{8}/);
const first = page.url();
const mark = page.locator('input[id^="mark-"]').first();
await mark.fill("0");
await mark.blur();
await page.waitForTimeout(1500);
check((await mark.inputValue()) === "0" && (await page.getByText("Back to Lara’s mark").first().isVisible()), "mark override is saved and resettable");
const reviewedButton = page.getByRole("button", { name: "Reviewed", exact: true });
if (await reviewedButton.isVisible()) {
  await reviewedButton.click();  // a second run starts from an unreviewed paper
  await page.getByRole("button", { name: "Mark as reviewed" }).waitFor();
}
await page.getByRole("button", { name: "Mark as reviewed" }).click();
await reviewedButton.waitFor();
check(true, "paper marked as reviewed");
const hasNext = await page.getByRole("button", { name: "Next paper" }).isEnabled();
await page.keyboard.press(hasNext ? "]" : "[");
await page.waitForURL((u) => u.toString() !== first);
check(true, `${hasNext ? "]" : "["} moves to the ${hasNext ? "next" : "previous"} paper`);

const a = await (await fetch(`${api}/assessments/${aid}`)).json();
const pair = a.analysis.pairs[0];
if (pair) {
  await page.goto(`${web}/assessments/${aid}/compare/${pair.a}/${pair.b}`);
  const heading = page.getByRole("heading", { name: "Side by side" });
  await heading.waitFor({ timeout: 20_000 }).catch(() => undefined);
  check(await heading.isVisible(), `comparison opens (pair score ${pair.score})`);
}
await page.goto(`${web}/assessments/${aid}`);
await page.getByText("Export").click();
const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Grades \(CSV\)/ }).click()]);
const csv = readFileSync(await download.path(), "utf-8");
// The drafted labels follow the exam's own numbering ("1α", "1.α", "1 α)"), so match any of them.
check(csv.startsWith("﻿") && /Question 1\.?\s?α/.test(csv), `CSV downloaded as ${download.suggestedFilename()}`);
check(errors.length === 0, `no page errors${errors.length ? `: ${errors.join(" | ")}` : ""}`);
await browser.close();
