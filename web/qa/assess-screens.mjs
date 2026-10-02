// Screenshots of the dashboard and the assessment pages:
//   node qa/assess-screens.mjs <assessmentId> [web] [outDir] [lang]
// Shoots the overview, the lists, setup, every workspace tab, one paper (each tab) and a comparison, at three sizes.
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const [aid, web = "http://localhost:3100", out = "/tmp/lara-qa", lang = "el"] = process.argv.slice(2);
if (!aid) throw new Error("usage: node qa/assess-screens.mjs <assessmentId> [web] [outDir] [lang]");
mkdirSync(out, { recursive: true });
const api = process.env.API ?? "http://localhost:8100";
const assessment = await (await fetch(`${api}/assessments/${aid}`)).json();
const graded = assessment.papers.filter((p) => p.status === "graded");
const paper = graded.find((p) => p.review_flags > 0) ?? graded[0];
const pair = assessment.analysis.pairs[0];

const browser = await chromium.launch({ channel: "chrome", headless: true });
const sizes = { desktop: { width: 1440, height: 900 }, tablet: { width: 1024, height: 768 }, phone: { width: 390, height: 844 } };
for (const [name, viewport] of Object.entries(sizes)) {
  const ctx = await browser.newContext({ viewport });
  await ctx.addCookies([{ name: "lara-lang", value: lang, url: web }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const shot = async (path, file, full = true) => {
    await page.goto(`${web}${path}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${out}/${name}-${file}.png`, fullPage: full });
  };
  await shot("/", "overview");
  await shot("/assessments", "assessments");
  await shot("/new", "chooser");
  await shot("/new/assessment", "new-assessment");
  for (const tab of ["overview", "students", "rubric", "integrity"]) await shot(`/assessments/${aid}?tab=${tab}`, `ws-${tab}`);
  if (paper) {
    for (const tab of ["grading", "integrity", "transcript"]) await shot(`/assessments/${aid}/students/${paper.id}?tab=${tab}`, `paper-${tab}`, false);
  }
  if (pair) await shot(`/assessments/${aid}/compare/${pair.a}/${pair.b}`, "compare");
  if (errors.length) console.log(name, "errors:", [...new Set(errors)].slice(0, 8));
  await ctx.close();
}
await browser.close();
console.log("done", out);
