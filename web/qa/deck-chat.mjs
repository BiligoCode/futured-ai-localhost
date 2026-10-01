// Live QA of the chat panel against the real model: node qa/deck-chat.mjs <deckId> [web] [api]
import { chromium } from "playwright";

const [deckId, web = "http://localhost:3100", api = "http://localhost:8001"] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

await page.goto(`${web}/decks/${deckId}`);
await page.waitForSelector(".slide-editor .ProseMirror");
const before = await (await fetch(`${api}/decks/${deckId}`)).json();

// Type in slide 2 right before asking, so the merge has a local edit to preserve.
const second = page.locator(".slide-editor .ProseMirror").nth(1);
await second.click();
await page.keyboard.press("End");
await page.keyboard.type(" ΤΟΠΙΚΟ");

const box = page.getByRole("textbox", { name: /Ρωτήστε τη Lara|Ask Lara/ });
await box.fill("Κάνε τον τίτλο της πρώτης διαφάνειας κόκκινο και πρόσθεσε μια διαφάνεια σύνοψης στο τέλος. Επίσης, τι είναι η πολυπλοκότητα O(n²); Σύντομα.");
const t0 = Date.now();
await page.getByRole("button", { name: /Αποστολή|Send/ }).click();
await page.waitForSelector("text=/Σκέφτεται|Thinking/");
await page.waitForFunction(() => !document.body.innerText.match(/Σκέφτεται…|Thinking…/), null, { timeout: 90000 });
console.log(`reply in ${((Date.now() - t0) / 1000).toFixed(1)}s`);

const chips = await page.locator("button.rounded-full.text-xs").allInnerTexts();
console.log("chips:", chips);
await page.waitForTimeout(1500);
const after = await (await fetch(`${api}/decks/${deckId}`)).json();
console.log("title red:", /color: #c93838/.test(after.slides[0].html), "| slides", before.slides.length, "→", after.slides.length, "| local edit kept:", after.slides[1].html.includes("ΤΟΠΙΚΟ"));
console.log("assistant reply:", after.chat.at(-1).content.slice(0, 120));

// Type more in slide 2 *after* the AI edit, then undo the AI edit → only the AI's work is reverted.
await page.locator(".slide-editor .ProseMirror").nth(1).click();
await page.keyboard.press("End");
await page.keyboard.type(" ΜΕΤΑ");
await page.getByRole("button", { name: /Αναίρεση αυτής της αλλαγής|Undo this change/ }).click();
await page.waitForTimeout(1500);
const undone = await (await fetch(`${api}/decks/${deckId}`)).json();
console.log("after undo: slides", undone.slides.length, "| title red:", /color: #c93838/.test(undone.slides[0].html), "| local edits kept:", undone.slides[1].html.includes("ΤΟΠΙΚΟ") && undone.slides[1].html.includes("ΜΕΤΑ"));
console.log("active slide still valid (chip):", await page.locator("form span", { hasText: /Διαφάνεια \d|Slide \d/ }).first().isVisible());
console.log("page errors:", errors.length ? errors : "none");
await browser.close();
