import type { Project, SceneDraft } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
  }
  return "Something went wrong";
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the API running?");
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
export const createProject = (form: FormData) => request<Project>("/projects", { method: "POST", body: form });
export const saveStoryboard = (id: string, scenes: SceneDraft[]) =>
  request<Project>(`/projects/${id}/storyboard`, json("PUT", { scenes }));
export const startRender = (id: string) => request<Project>(`/projects/${id}/render`, { method: "POST" });
export const retryScene = (id: string, sid: string) =>
  request<Project>(`/projects/${id}/scenes/${sid}/retry`, { method: "POST" });
export const reviseScene = (id: string, sid: string, instruction: string) =>
  request<Project>(`/projects/${id}/scenes/${sid}/revise`, json("POST", { instruction }));
export const getSceneCode = (id: string, sid: string) => request<string>(`/projects/${id}/scenes/${sid}/code`);
export const videoUrl = (id: string, sid: string, version: number) =>
  `${API_URL}/projects/${id}/scenes/${sid}/video?v=${version}`;

export const updateNarration = (id: string, sid: string, narration: string) =>
  request<Project>(`/projects/${id}/scenes/${sid}`, json("PATCH", { narration }));
export const generateAiVoice = (id: string, sid: string) =>
  request<Project>(`/projects/${id}/scenes/${sid}/voice/ai`, { method: "POST" });
export const generateAllAiVoice = (id: string) => request<Project>(`/projects/${id}/voice/ai-all`, { method: "POST" });
export function uploadRecording(id: string, sid: string, blob: Blob) {
  const form = new FormData();
  form.append("file", blob, "take.webm");
  return request<Project>(`/projects/${id}/scenes/${sid}/voice/recording`, { method: "POST", body: form });
}
export const clearVoice = (id: string, sid: string) =>
  request<Project>(`/projects/${id}/scenes/${sid}/voice`, { method: "DELETE" });
export const exportProject = (id: string) => request<{ url: string }>(`/projects/${id}/export`, { method: "POST" });
export const audioUrl = (id: string, sid: string, bust: number) =>
  `${API_URL}/projects/${id}/scenes/${sid}/audio?v=${bust}`;
export const exportUrl = (id: string, bust: number) => `${API_URL}/projects/${id}/export.mp4?v=${bust}`;
