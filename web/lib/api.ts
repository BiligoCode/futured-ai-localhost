import type { Project } from "./types";

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
