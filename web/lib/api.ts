import { LANG_COOKIE, MESSAGES, parseLang } from "./messages";
import type { ChatResult, CutKind, Deck, DeckSummary, DeckUpdate, EmbedMode, ExportFormat, Hold, Project, ReviseResult, SceneDraft } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

/** The interface language, read from the cookie the language switch writes (the server translates its errors). */
function uiLang() {
  if (typeof document === "undefined") return parseLang(null);
  return parseLang(document.cookie.match(new RegExp(`(?:^|; )${LANG_COOKIE}=([^;]*)`))?.[1]);
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
  }
  return MESSAGES[uiLang()].somethingWrong;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    const headers = new Headers(init?.headers);
    headers.set("X-Lara-Lang", uiLang());
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, MESSAGES[uiLang()].cannotReach);
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, describe(detail));
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const listProjects = () => request<Project[]>("/projects");
export const getProject = (id: string) => request<Project>(`/projects/${id}`);
export const createProject = (form: FormData, signal?: AbortSignal) =>
  request<Project>("/projects", { method: "POST", body: form, signal });
export const deleteProject = (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" });
export const getMaterial = (id: string) => request<string>(`/projects/${id}/material`);
export const reopenScript = (id: string) => request<Project>(`/projects/${id}/reopen`, { method: "POST" });
export const cancelProject = (id: string) => request<Project>(`/projects/${id}/cancel`, { method: "POST" });
export const saveStoryboard = (id: string, scenes: SceneDraft[]) =>
  request<Project>(`/projects/${id}/storyboard`, json("PUT", { scenes }));
export const startRender = (id: string) => request<Project>(`/projects/${id}/render`, { method: "POST" });
export const composeVideo = (id: string) => request<Project>(`/projects/${id}/compose`, { method: "POST" });

export const reviseVideo = (id: string, instruction: string, cut: CutKind, atSeconds: number | null) =>
  request<ReviseResult>(`/projects/${id}/revise`, json("POST", { instruction, cut, at_seconds: atSeconds }));

export const generateAiNarration = (id: string) => request<Project>(`/projects/${id}/narration/ai`, { method: "POST" });
export const removeNarration = (id: string) => request<Project>(`/projects/${id}/narration`, { method: "DELETE" });
export const setCaptions = (id: string, captions: boolean) =>
  request<Project>(`/projects/${id}/settings`, json("PATCH", { captions }));
export function uploadTake(id: string, blob: Blob, fromScene: string, holds: Hold[]) {
  const form = new FormData();
  form.append("file", blob, "take.webm");
  form.append("from_scene", fromScene);
  form.append("holds", JSON.stringify(holds));
  return request<Project>(`/projects/${id}/narration/recording`, { method: "POST", body: form });
}

export const cutUrl = (id: string, kind: CutKind, version: number) =>
  `${API_URL}/projects/${id}/${kind === "final" ? "export" : "preview"}.mp4?v=${version}`;

// --- Slides ------------------------------------------------------------------------------------------------------

export const listDecks = () => request<DeckSummary[]>("/decks");
export const getDeck = (id: string) => request<Deck>(`/decks/${id}`);
export const createDeck = (form: FormData) => request<Deck>("/decks", { method: "POST", body: form });
export const saveDeck = (id: string, body: DeckUpdate) => request<Deck>(`/decks/${id}`, json("PUT", body));
/** Fire-and-forget save for when the page is being left; `keepalive` lets the browser finish it after unload. */
export const saveDeckOnLeave = (id: string, body: DeckUpdate) => {
  void fetch(`${API_URL}/decks/${id}`, { ...json("PUT", body), keepalive: true, headers: { "Content-Type": "application/json", "X-Lara-Lang": uiLang() } }).catch(() => undefined);
};
export const deleteDeck = (id: string) => request<void>(`/decks/${id}`, { method: "DELETE" });
export const chatDeck = (
  id: string,
  body: { message: string; slide_id: string | null; selection: string | null },
  signal?: AbortSignal,
) => request<ChatResult>(`/decks/${id}/chat`, { ...json("POST", body), signal });
export const embedAnimation = (deckId: string, body: { project_id: string; slide_id: string | null; mode: EmbedMode }) =>
  request<Deck>(`/decks/${deckId}/embed`, json("POST", body));
export const exportDeck = (id: string, format: ExportFormat) =>
  request<{ url: string; filename: string }>(`/decks/${id}/export`, json("POST", { format }));
export const posterUrl = (deckId: string, projectId: string) => `${API_URL}/decks/${deckId}/posters/${projectId}.jpg`;
export const exportUrl = (url: string) => `${API_URL}${url}`;
