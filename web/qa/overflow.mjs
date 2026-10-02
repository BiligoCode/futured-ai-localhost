import { chromium } from "playwright";
// Horizontal overflow at phone width: node qa/overflow.mjs <assessmentId> <paperId> [web]
const [aid, pid, webArg] = process.argv.slice(2);
const web = webArg ?? "http://localhost:3100";
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
await ctx.addCookies([{ name: "lara-lang", value: "el", url: web }]);
const page = await ctx.newPage();
for (const path of ["/", "/assessments", "/new", "/new/assessment", `/assessments/${aid}?tab=overview`, `/assessments/${aid}?tab=students`, `/assessments/${aid}?tab=rubric`, `/assessments/${aid}?tab=integrity`, `/assessments/${aid}/students/${pid}`]) {
  await page.goto(web + path); await page.waitForLoadState("networkidle"); await page.waitForTimeout(400);
  const r = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const offenders = [];
    for (const el of document.querySelectorAll("body *")) {
      const b = el.getBoundingClientRect();
      if (b.right > vw + 1 && b.width > 0) {
        let p = el.parentElement, clipped = false;
        while (p) { const s = getComputedStyle(p); if (["auto", "scroll", "hidden"].includes(s.overflowX)) { clipped = true; break; } p = p.parentElement; }
        if (!clipped) offenders.push(`${el.tagName.toLowerCase()}.${(el.className?.baseVal ?? el.className ?? "").toString().slice(0, 60)} right=${Math.round(b.right)}`);
      }
    }
    return { scroll: document.documentElement.scrollWidth, vw, offenders: offenders.slice(0, 6) };
  });
  console.log(path, r.scroll, r.vw, r.offenders);
}
await browser.close();
