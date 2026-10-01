// Deletion flows: node qa/deck-delete.mjs [web] [api]
import { chromium } from "playwright";

const [web = "http://localhost:3100", api = "http://localhost:8001"] = process.argv.slice(2);
const json = (r) => r.json();
// A fresh deck with one embedded animation (faked as rendered) and one linked draft.
const fd = new FormData(); fd.append("title", "Προς διαγραφή"); fd.append("language", "el");
const deck = await fetch(`${api}/decks`, { method: "POST", body: fd }).then(json);
const decks = await fetch(`${api}/decks`).then(json);
const other = decks.find((d) => d.id !== deck.id);
const embeddedProject = (await fetch(`${api}/decks/${other.id}`).then(json)).animations.find((a) => a.embedded && a.status === "ready");

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("dialog", (d) => d.accept());

// 1. Delete an animation that is embedded in the other deck → placeholder, export still works.
await fetch(`${api}/projects/${embeddedProject.project_id}`, { method: "DELETE" });
await page.goto(`${web}/decks/${other.id}`);
await page.waitForSelector(".slide-editor .ProseMirror");
console.log("placeholder shown:", await page.getByText(/Η κινούμενη εικόνα διαγράφηκε|Animation deleted/).first().isVisible());
const exp = await fetch(`${api}/decks/${other.id}/export`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ format: "pdf" }) });
console.log("export after deletion:", exp.status, (await exp.json()).filename);

// 2. Delete the fresh deck from the dashboard; the other deck's animations are untouched.
await page.goto(`${web}/`);
await page.waitForSelector("text=Προς διαγραφή");
const tile = page.locator("li", { hasText: "Προς διαγραφή" }).first();
await tile.hover();
await tile.getByRole("button", { name: /Διαγραφή διαφανειών|Delete slides/ }).click();
await page.getByText("Προς διαγραφή").first().waitFor({ state: "detached", timeout: 10000 });
console.log("deck gone from dashboard:", (await page.getByText("Προς διαγραφή").count()) === 0, "| API 404:", (await fetch(`${api}/decks/${deck.id}`)).status === 404);
console.log("other deck's animations still exist:", (await fetch(`${api}/projects`).then(json)).some((p) => p.deck_id === other.id));
await browser.close();
