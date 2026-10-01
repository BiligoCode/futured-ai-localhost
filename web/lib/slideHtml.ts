/** The slide contract shared with the API (`api/app/slides_html.py`): sizes, palette and plain-text helpers.
 * The HTML these helpers read is always the server-sanitised subset, so simple tag stripping is safe. */

export const SLIDE_W = 1280;
export const SLIDE_H = 720;

export const PALETTE: { name: string; hex: string }[] = [
  { name: "ink", hex: "#18212e" },
  { name: "muted", hex: "#566173" },
  { name: "accent", hex: "#1b6f8c" },
  { name: "green", hex: "#0f7b6c" },
  { name: "gold", hex: "#74490a" },
  { name: "red", hex: "#c93838" },
  { name: "purple", hex: "#6d3fb8" },
  { name: "amber", hex: "#e2a13b" },
];

export const SIZES = [
  { label: "S", px: 20 },
  { label: "M", px: 26 },
  { label: "L", px: 34 },
  { label: "XL", px: 44 },
] as const;

export const BODY_PX = 26;
const TITLE_CHARS = 60;

const ENTITIES: Record<string, string> = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " " };

function decode(text: string): string {
  return text.replace(/&(amp|lt|gt|quot|#39|nbsp);/g, (m) => ENTITIES[m] ?? m);
}

function tidy(text: string): string {
  return decode(text).replace(/\s+/g, " ").trim();
}

/** Plain text of a slide: one line per block, `- ` before list items. */
export function slideText(html: string): string {
  const lines = html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<li[^>]*>/gi, "\n- ")
    .replace(/<\/(h1|h2|p|li)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .split("\n")
    .map((line) => (line.startsWith("- ") ? "- " + tidy(line.slice(2)) : tidy(line)))
    .filter((line) => line && line !== "-");
  return lines.join("\n");
}

/** The slide's title: its first heading, else the first words of its text. */
export function slideTitle(html: string): string {
  const heading = /<h[12][^>]*>([\s\S]*?)<\/h[12]>/i.exec(html);
  if (heading) {
    const text = tidy(heading[1].replace(/<[^>]+>/g, ""));
    if (text) return text;
  }
  return slideText(html).replace(/\n- |\n/g, " ").replace(/^- /, "").slice(0, TITLE_CHARS).trim();
}
