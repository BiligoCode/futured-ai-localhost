// Accessible-name check: node qa/a11y.mjs <url>...  (lists buttons/links/inputs without a name)
import { chromium } from "playwright";
const urls = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
for (const url of urls) {
  await page.goto(url); await page.waitForLoadState("networkidle"); await page.waitForTimeout(500);
  const unnamed = await page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll("button, a[href], input:not([type=hidden]), textarea, select, [role=button], [role=separator]")) {
      const name = el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.getAttribute("title") || el.textContent?.trim() ||
        (el.id && document.querySelector(`label[for="${el.id}"]`)?.textContent) || el.closest("label")?.textContent?.trim() || el.getAttribute("placeholder");
      if (!name) out.push(el.outerHTML.slice(0, 120));
    }
    return out;
  });
  console.log(url.replace(/^http:\/\/localhost:3100/, ""), "→", unnamed.length ? unnamed : "all named");
}
await browser.close();
