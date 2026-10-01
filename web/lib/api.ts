import { LANG_COOKIE, MESSAGES, parseLang } from "./messages";
import type { Cut, CutKind, Hold, Project, ReviseResult, SceneDraft } from "./types";

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

/** A short hash of what a cut contains (its signature), so a rebuilt video never reuses a cached URL. */
function contentTag(signature: string): string {
  let h = 5381;
  for (let i = 0; i < signature.length; i++) h = ((h << 5) + h + signature.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

// The version alone is not enough: removing all narration resets the final video to version 0, so the next
// narrated video is version 1 again and the browser would play the old one from its cache.
export const cutUrl = (id: string, kind: CutKind, cut: Pick<Cut, "version" | "signature">) =>
  `${API_URL}/projects/${id}/${kind === "final" ? "export" : "preview"}.mp4?v=${cut.version}.${contentTag(cut.signature)}`;
