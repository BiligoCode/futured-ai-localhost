// Screenshot set for visual QA: node qa/screens.mjs <deckId> <projectId> [web]
import { chromium } from "playwright";

const [deckId, projectId, web = "http://localhost:3100"] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const sizes = { desktop: { width: 1440, height: 900 }, tablet: { width: 1024, height: 768 }, phone: { width: 390, height: 844 } };
for (const [name, viewport] of Object.entries(sizes)) {
  const ctx = await browser.newContext({ viewport, locale: "el" });
  const page = await ctx.newPage();
  const shot = async (path, file) => {
    await page.goto(`${web}${path}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(600);
    await page.screenshot({ path: `/tmp/opencode/qa-${name}-${file}.png` });
  };
  await shot("/", "dashboard");
  await shot("/new", "chooser");
  await shot("/new/slides", "newdeck");
  await shot(`/decks/${deckId}`, "deck");
  await shot(`/projects/${projectId}`, "project");
  if (name === "desktop") {
    await page.getByRole("button", { name: /Προσθήκη στις διαφάνειες|Add to slides/ }).click();
    await page.getByRole("dialog").waitFor();
    await page.screenshot({ path: `/tmp/opencode/qa-${name}-embed.png` });
  }
  await ctx.close();
}
await browser.close();
console.log("done");
