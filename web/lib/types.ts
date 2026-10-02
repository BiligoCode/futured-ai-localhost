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

// --- Assessments -------------------------------------------------------------------------------------------------

export type QuestionType = "true_false" | "multiple_choice" | "numeric" | "short" | "open";
export type PaperStatus = "queued" | "reading" | "read" | "grading" | "graded" | "failed";
export type Confidence = "high" | "medium" | "low";
export type ResultStatus = "correct" | "incorrect" | "partial" | "unanswered" | "unreadable";
export type GradeScale = 10 | 20 | 100;
export type KeyFrom = "exam" | "lara" | "professor";
export type RubricStatus = "none" | "drafting" | "draft" | "confirmed" | "failed";
export type AiLevel = "low" | "some" | "strong" | "insufficient";
export type Verdict = "likely_copied" | "possibly" | "independent" | "";

export interface Criterion {
  id: string;
  text: string;
  points: number;
}

export interface Question {
  id: string;
  label: string;
  type: QuestionType;
  prompt: string;
  points: number;
  options: string[];
  answer: string;
  tolerance: number;
  model_answer: string;
  criteria: Criterion[];
  partial: boolean;
  key_from: KeyFrom;
}

export interface Rubric {
  status: RubricStatus;
  source: "exam" | "papers" | "manual";
  questions: Question[];
  version: number;
  note: string;
  error: string | null;
}

export interface PageInfo {
  n: number;
  method: "vision" | "text";
  width: number;
  height: number;
  dhash: string;
}

export interface Block {
  label: string | null;
  prompt: string | null;
  text: string;
  final: string | null;
}

export interface PageReading {
  n: number;
  blocks: Block[];
  text: string;
  notes: string;
}

export interface QuestionResult {
  question_id: string;
  page: number | null;
  answer: string;
  final: string | null;
  second_final: string | null;
  status: ResultStatus;
  correct: boolean | null;
  points: number;
  max_points: number;
  criteria: Record<string, number>;
  feedback: string;
  errors: string[];
  specifics: string[];
  confidence: Confidence;
  flags: string[];
  override_points: number | null;
  override_final: string | null;
  comment: string;
  model_points: number | null;
  matches_key: boolean | null;
  model_feedback: string;
  model_confidence: Confidence;
}

export interface Signal {
  code: string;
  strength: number;
  detail: Record<string, unknown>;
}

export interface AiAnalysis {
  score: number;
  level: AiLevel;
  words: number;
  signals: Signal[];
  note: string;
  likelihood: number;
}

export interface Finding {
  code: string;
  severity: "info" | "warn" | "alert";
  detail: Record<string, unknown>;
}

export interface Forensics {
  kind: "scanned" | "typed" | "mixed" | "image";
  sha256: string;
  metadata: Record<string, string>;
  xmp: Record<string, string>;
  file_id: string | null;
  fonts: string[];
  findings: Finding[];
}

export interface Paper {
  id: string;
  created_at: string;
  filename: string;
  source: "pdf" | "jpg" | "png";
  sha256: string;
  split_from: string | null;
  student_name: string;
  student_id: string;
  name_from: "file" | "paper" | "professor";
  status: PaperStatus;
  error: string | null;
  failed_stage: "reading" | "grading" | null;
  pages: PageInfo[];
  reading: PageReading[];
  results: QuestionResult[];
  summary: string;
  rubric_version: number;
  ai: AiAnalysis | null;
  forensics: Forensics | null;
  reviewed: boolean;
  note: string;
  updated_at: string | null;
}

export interface PaperRow {
  id: string;
  filename: string;
  student_name: string;
  student_id: string;
  status: PaperStatus;
  error: string | null;
  page_count: number;
  points: number | null;
  max_points: number;
  grade: number | null;
  ai_score: number | null;
  ai_level: AiLevel | null;
  ai_signals: string[];
  findings: string[];
  copy_score: number | null;
  copy_match: string | null;
  alerts: number;
  review_flags: number;
  needs_review: boolean;
  reviewed: boolean;
  rubric_version: number;
  marks: Record<string, number>;
  picks: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  code: string;
  strength: number;
  question_id: string | null;
  detail: Record<string, unknown>;
}

/** Something Lara found in both papers, in each paper's own words (checked in the text). */
export interface SharedItem {
  question_id: string | null;
  what: string;
  a: string;
  b: string;
  rare: boolean;
}

export interface PairResult {
  a: string;
  b: string;
  score: number;
  evidence: Evidence[];
  verdict: Verdict;
  explanation: string;
  shared?: SharedItem[];
}

export interface Cluster {
  question_id: string;
  kind: "mistake" | "detail";
  label: string;
  members: string[];
}

export interface Analysis {
  status: "idle" | "running" | "done" | "failed";
  stale: boolean;
  computed_at: string | null;
  error: string | null;
  covered: string[];
  pairs: PairResult[];
  clusters: Cluster[];
  insights: string;
  recommendations: string[];
  question_insights: Record<string, string>;
}

export interface HistogramBin {
  start: number;
  end: number;
  count: number;
}

export interface QuestionStats {
  question_id: string;
  answered: number;
  graded: number;
  mean_pct: number | null;
  correct_rate: number | null;
  distribution: Record<string, number>;
}

export interface Stats {
  total: number;
  counts: Partial<Record<PaperStatus, number>>;
  graded: number;
  busy: boolean;
  needs_review: number;
  reviewed: number;
  flagged: number;
  mean: number | null;
  median: number | null;
  sd: number | null;
  min: number | null;
  max: number | null;
  pass_rate: number | null;
  histogram: HistogramBin[];
  questions: QuestionStats[];
}

export interface Assessment {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  course: string;
  language: Language;
  scale: GradeScale;
  instructions: string;
  paused: boolean;
  rubric: Rubric;
  papers: PaperRow[];
  analysis: Analysis;
  stats: Stats;
  exam_chars: number;
}

export interface AssessmentSummary {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  course: string;
  language: Language;
  scale: GradeScale;
  rubric_status: RubricStatus;
  papers: number;
  graded: number;
  busy: boolean;
  paused: boolean;
  mean: number | null;
  needs_review: number;
  flagged: number;
  histogram: number[];
}

export interface UploadResult {
  assessment: Assessment;
  added: PaperRow[];
  skipped: { filename: string; reason: string }[];
}

export interface CompareResult {
  a: Paper;
  b: Paper;
  pair: PairResult | null;
}

export type QuestionIn = Omit<Question, "id" | "criteria"> & { id: string | null; criteria: { id: string | null; text: string; points: number }[] };

export interface ResultOverride {
  override_points?: number | null;
  override_final?: string | null;
  comment?: string | null;
  clear_points?: boolean;
  clear_final?: boolean;
}

export interface PaperUpdate {
  student_name?: string;
  student_id?: string;
  reviewed?: boolean;
  note?: string;
  results?: Record<string, ResultOverride>;
}
