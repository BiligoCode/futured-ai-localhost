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
  captions: boolean;
  preview_outdated: boolean;
  final_outdated: boolean;
  deck_id: string | null;
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

// --- Slides ------------------------------------------------------------------------------------------------------

export type EditOp = "replace" | "insert_after" | "delete" | "move";
export type AnimationStatus = "draft" | "creating" | "ready" | "missing";
export type EmbedMode = "append" | "new_after" | "new_end";
export type ExportFormat = "pdf" | "docx";

export interface Slide {
  id: string;
  html: string;
  video: string | null;
}

export interface EditLog {
  op: EditOp;
  slide_id: string;
  title: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  edits: EditLog[];
  at: string;
}

export interface AnimationRef {
  project_id: string;
  title: string;
  status: AnimationStatus;
  cut: CutKind | null;
  version: number;
  signature: string;
  duration: number;
  embedded: boolean;
}

export interface Deck {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  language: Language;
  slides: Slide[];
  chat: ChatMessage[];
  version: number;
  animations: AnimationRef[];
}

export interface DeckSummary {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  language: Language;
  slide_count: number;
  animation_count: number;
  first_slide_html: string;
}

export interface SlideIn {
  id: string | null;
  html: string;
  video: string | null;
}

export interface DeckUpdate {
  title: string;
  slides: SlideIn[];
  version: number;
}

export interface ChatResult {
  deck: Deck;
  reply: string;
  edits: EditLog[];
}
