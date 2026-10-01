// End-to-end: deck → Create animation → (script drafted by the real model) → mark rendered → Add to slides.
//   node qa/deck-animation.mjs <deckId> [web] [api] [dataDir]
import { execSync } from "node:child_process";
import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";

const [deckId, web = "http://localhost:3100", api = "http://localhost:8001", dataDir = "../data"] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

// 1. Deck → Create animation → setup form with the slides attached.
await page.goto(`${web}/decks/${deckId}`);
await page.waitForSelector(".slide-editor .ProseMirror");
await page.getByRole("button", { name: /Δημιουργία κινούμενης εικόνας|Create animation/ }).click();
await page.waitForURL(/\/new\/animation\?deck=/);
await page.waitForSelector("#concept");
await page.screenshot({ path: "/tmp/opencode/setup-from-deck.png" });
console.log("setup from deck:", await page.locator("input[name=deck_id]").count(), "| language el:", await page.locator('input[name=language][value=el]').isChecked());

// 2. Draft the script with the real model.
await page.fill("#concept", "Ταξινόμηση φυσαλίδας");
const t0 = Date.now();
await page.getByRole("button", { name: /Σύνταξη σεναρίου|Draft script/ }).click();
await page.waitForURL(/\/projects\//, { timeout: 120000 });
const projectId = page.url().split("/projects/")[1];
console.log(`script drafted in ${((Date.now() - t0) / 1000).toFixed(1)}s → project ${projectId}`);
const project = await (await fetch(`${api}/projects/${projectId}`)).json();
console.log("deck_id stored:", project.deck_id === deckId, "| deck text in material:", existsSync(`${dataDir}/projects/${projectId}/deck.txt`));

// 3. Pretend the animation finished: mark scenes rendered and drop in a clip.
const file = `${dataDir}/projects/${projectId}/project.json`;
const p = JSON.parse(readFileSync(file, "utf8"));
p.stage = "scenes";
for (const s of p.scenes) { s.render_status = "done"; s.code_version = 1; }
p.preview = { status: "done", version: 1, signature: p.scenes.map((s) => `${s.id}:1`).join("|"), duration: 4, segments: [], error: null };
writeFileSync(file, JSON.stringify(p, null, 2));
execSync(`ffmpeg -v error -y -f lavfi -i testsrc=size=1280x720:rate=30:duration=4 -pix_fmt yuv420p ${dataDir}/projects/${projectId}/preview.mp4`);

// 4. Project page → Add to slides → dialog → new slide after slide 2.
await page.reload();
await page.getByRole("button", { name: /Προσθήκη στις διαφάνειες|Add to slides/ }).click();
const dialog = page.getByRole("dialog");
await dialog.waitFor();
await dialog.locator("label:has(input[name=slide])").nth(1).click({ noWaitAfter: true });
await dialog.getByText(/Νέα διαφάνεια μετά|New slide after/).click({ noWaitAfter: true });
await page.screenshot({ path: "/tmp/opencode/embed-dialog.png" });
const before = await (await fetch(`${api}/decks/${deckId}`)).json();
await dialog.getByRole("button", { name: /^Προσθήκη$|^Add$/ }).click();
await page.waitForURL(new RegExp(`/decks/${deckId}`), { timeout: 20000 });
await page.waitForSelector(".slide-video video");
const after = await (await fetch(`${api}/decks/${deckId}`)).json();
console.log("slides", before.slides.length, "→", after.slides.length, "| new slide 3 has video:", after.slides[2].video === projectId, "| title:", after.slides[2].html);
console.log("poster exists:", existsSync(`${dataDir}/decks/${deckId}/posters/${projectId}.jpg`));
const ref = after.animations.find((a) => a.project_id === projectId);
console.log("animation ref:", ref && { status: ref.status, cut: ref.cut, embedded: ref.embedded });
const videoSrc = await page.locator(".slide-video video").first().getAttribute("src");
console.log("video src ok:", videoSrc?.includes(`/projects/${projectId}/preview.mp4`), "| poster attr ok:", (await page.locator(".slide-video video").first().getAttribute("poster"))?.includes(`/posters/${projectId}.jpg`));

// 5. Animations menu lists it; remove from slide works.
await page.getByText(/κινούμενες εικόνες|κινούμενη εικόνα|animations?$/).first().click();
await page.waitForTimeout(300);
console.log("menu lists project:", await page.locator(`a[href="/projects/${projectId}"]`).isVisible());
await page.screenshot({ path: "/tmp/opencode/embedded.png" });
await page.getByRole("button", { name: /Αφαίρεση από τη διαφάνεια|Remove from slide/ }).first().click();
await page.waitForTimeout(1500);
const removed = await (await fetch(`${api}/decks/${deckId}`)).json();
console.log("removed from slide (slide kept):", removed.slides[2].video === null && removed.slides.length === after.slides.length);
console.log("page errors:", errors.length ? errors : "none");
await browser.close();
