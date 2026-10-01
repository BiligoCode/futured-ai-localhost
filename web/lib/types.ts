export type Language = "el" | "en";
export type RenderStatus = "pending" | "generating" | "rendering" | "repairing" | "done" | "failed";
export type AudioStatus = "none" | "generating" | "done" | "failed";
export type AudioSource = "ai" | "professor";
export type CutStatus = "none" | "building" | "done" | "failed";
export type CutKind = "preview" | "final";
export type DurationRange = "short" | "medium" | "long";

export interface Hold {
  at: number;
  duration: number;
}

export interface Scene {
  id: string;
  title: string;
  visual: string;
  narration: string;
  code_version: number;
  render_status: RenderStatus;
  attempts: number;
  last_error: string | null;
  layout_issues: string[];
  audio_source: AudioSource | null;
  audio_status: AudioStatus;
  audio_version: number;
  holds: Hold[];
  audio_stale: boolean;
}

export interface SceneDraft {
  id?: string | null;
  title: string;
  visual: string;
  narration: string;
}

export interface Segment {
  scene_id: string;
  start: number;
  end: number;
}

export interface Cut {
  status: CutStatus;
  version: number;
  signature: string;
  duration: number;
  segments: Segment[];
  error: string | null;
}

export interface Project {
  id: string;
  created_at: string;
  title: string;
  concept: string;
  style: string;
  duration: DurationRange;
  language: Language;
  stage: "storyboard" | "scenes";
  scenes: Scene[];
  preview: Cut;
  final: Cut;
  narrating: boolean;
  preview_outdated: boolean;
  final_outdated: boolean;
}

export interface EditSummary {
  scene_id: string;
  start: number | null;
  end: number | null;
  summary: string;
  animation: boolean;
  narration: boolean;
}

export interface ReviseResult {
  project: Project;
  edits: EditSummary[];
}
