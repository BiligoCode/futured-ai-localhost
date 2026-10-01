export type Language = "el" | "en";
export type RenderStatus = "pending" | "generating" | "rendering" | "repairing" | "done" | "failed";
export type AudioStatus = "none" | "generating" | "done" | "failed";
export type AudioSource = "ai" | "professor";

export interface Scene {
  id: string;
  title: string;
  visual: string;
  narration: string;
  code_version: number;
  render_status: RenderStatus;
  attempts: number;
  last_error: string | null;
  audio_source: AudioSource | null;
  audio_status: AudioStatus;
}

export interface SceneDraft {
  id?: string | null;
  title: string;
  visual: string;
  narration: string;
}

export interface Project {
  id: string;
  created_at: string;
  title: string;
  concept: string;
  style: string;
  tone: string;
  language: Language;
  stage: "storyboard" | "scenes";
  scenes: Scene[];
}
