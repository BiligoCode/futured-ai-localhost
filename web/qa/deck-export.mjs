// Export QA: node qa/deck-export.mjs <deckId> [web]
import { chromium } from "playwright";

const [deckId, web = "http://localhost:3100"] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

await page.goto(`${web}/decks/${deckId}`);
await page.waitForSelector(".slide-editor .ProseMirror");
for (const label of [/^PDF/, /^Word/]) {
  await page.locator("summary", { hasText: /Εξαγωγή|Export/ }).click();
  await page.screenshot({ path: "/tmp/opencode/export-menu.png" });
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }), page.getByRole("button", { name: label }).click()]);
  const path = `/tmp/opencode/dl-${download.suggestedFilename()}`;
  await download.saveAs(path);
  console.log("downloaded:", download.suggestedFilename(), "→", path);
}
console.log("page errors:", errors.length ? errors : "none");
await browser.close();
