// Interactive QA for the deck workspace against running dev servers.
//   node qa/deck-editor.mjs <deckId> [web=http://localhost:3100] [api=http://localhost:8001]
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

// 1. Type into the first slide → autosave → persisted.
const first = page.locator(".slide-editor .ProseMirror").first();
await first.click();
await page.keyboard.press("End");
await page.keyboard.type(" ΔΟΚΙΜΗ-1");
await page.waitForFunction(() => document.body.innerText.includes("Αποθηκεύτηκε") || document.body.innerText.includes("Saved"), null, { timeout: 5000 });
const after = await (await fetch(`${api}/decks/${deckId}`)).json();
console.log("typed text saved:", after.slides[0].html.includes("ΔΟΚΙΜΗ-1"), "version", before.version, "→", after.version);

// 2. Toolbar: select the word and make it bold → saved as <strong>.
await page.keyboard.down("Shift");
for (let i = 0; i < 9; i++) await page.keyboard.press("ArrowLeft");
await page.keyboard.up("Shift");
await page.getByRole("button", { name: /Έντονα|Bold/ }).click();
await page.waitForTimeout(1500);
const bolded = await (await fetch(`${api}/decks/${deckId}`)).json();
console.log("bold saved:", /<strong> ?ΔΟΚΙΜΗ-1<\/strong>/.test(bolded.slides[0].html));

// 3. Add a slide from the strip, then delete it and undo.
const count = () => page.locator(".slide-editor").count();
const n0 = await count();
await page.getByRole("button", { name: /Νέα διαφάνεια|Add slide/ }).first().click();
await page.waitForFunction((n) => document.querySelectorAll(".slide-editor").length === n + 1, n0);
await page.waitForTimeout(1200);
const added = await (await fetch(`${api}/decks/${deckId}`)).json();
console.log("slide added & saved:", added.slides.length === n0 + 1);
const thumb = page.locator("nav li").nth(1);
await thumb.hover();
await thumb.getByRole("button", { name: /Διαγραφή διαφάνειας|Delete slide/ }).click();
await page.waitForFunction((n) => document.querySelectorAll(".slide-editor").length === n, n0);
await page.getByRole("status").getByRole("button", { name: /Αναίρεση|Undo/ }).click();
await page.waitForFunction((n) => document.querySelectorAll(".slide-editor").length === n + 1, n0);
console.log("delete + undo restores:", (await count()) === n0 + 1);

// 4. Title edit.
await page.getByTitle(/Αλλαγή τίτλου|Edit title/).click();
await page.keyboard.press("Control+A");
await page.keyboard.type("Νέος τίτλος");
await page.keyboard.press("Enter");
await page.waitForTimeout(1300);
console.log("title saved:", (await (await fetch(`${api}/decks/${deckId}`)).json()).title === "Νέος τίτλος");

// 5. Reload: everything persists, no console errors.
await page.reload();
await page.waitForSelector(".slide-editor .ProseMirror");
console.log("after reload slides:", await count(), "title shown:", await page.getByText("Νέος τίτλος").first().isVisible());
console.log("page errors:", errors.length ? errors : "none");
await browser.close();
