import { chromium } from "playwright";
const [url] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage();
const seen = new Set();
page.on("console", (m) => { if (["warning", "error"].includes(m.type())) { const t = m.text().slice(0, 300); if (!seen.has(t)) { seen.add(t); console.log(`[${m.type()}]`, t); } } });
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 300)));
await page.goto(url); await page.waitForTimeout(4000);
await browser.close();
