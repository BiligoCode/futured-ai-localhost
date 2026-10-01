// node qa/shot.mjs <url> <out.png> [width] [height] [lang]
import { chromium } from "playwright";
const [url, out, w = "1440", h = "900", lang = "el"] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: +w, height: +h } });
await ctx.addCookies([{ name: "lara-lang", value: lang, url: new URL(url).origin }]);
const page = await ctx.newPage();
await page.goto(url); await page.waitForLoadState("networkidle"); await page.waitForTimeout(600);
await page.screenshot({ path: out });
await browser.close();
