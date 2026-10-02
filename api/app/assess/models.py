"""Assessments: an exam or project, its rubric, the students' papers and the class analysis (design §4)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import Language

QuestionType = Literal["true_false", "multiple_choice", "numeric", "short", "open"]
DEFINITIVE: frozenset[str] = frozenset({"true_false", "multiple_choice", "numeric", "short"})
PaperStatus = Literal["queued", "reading", "read", "grading", "graded", "failed"]
BUSY_STATUSES: frozenset[str] = frozenset({"queued", "reading", "grading"})
Confidence = Literal["high", "medium", "low"]
ResultStatus = Literal["correct", "incorrect", "partial", "unanswered", "unreadable"]
Scale = Literal[10, 20, 100]
SourceKind = Literal["pdf", "jpg", "png"]


class AssessmentNotFound(KeyError):
    pass


class PaperNotFound(KeyError):
    pass


# --- Rubric -----------------------------------------------------------------------------------------------------

class Criterion(BaseModel):
    id: str
    text: str
    points: float = Field(gt=0)


class Question(BaseModel):
    id: str
    label: str
    type: QuestionType
    prompt: str = Field(default="", max_length=2000)
    points: float = Field(gt=0)
    options: list[str] = []
    answer: str = ""
    tolerance: float = Field(default=0, ge=0)
    model_answer: str = Field(default="", max_length=6000)
    criteria: list[Criterion] = []
    partial: bool = False
    key_from: Literal["exam", "lara", "professor"] = "professor"


class Rubric(BaseModel):
    status: Literal["none", "drafting", "draft", "confirmed", "failed"] = "none"
    source: Literal["exam", "papers", "manual"] = "manual"
    questions: list[Question] = []
    version: int = 0
    note: str = ""
    error: str | None = None

    def question(self, question_id: str) -> Question | None:
        return next((q for q in self.questions if q.id == question_id), None)

    @property
    def max_points(self) -> float:
        return sum(q.points for q in self.questions)


# --- Papers -----------------------------------------------------------------------------------------------------

class PageInfo(BaseModel):
    n: int
    method: Literal["vision", "text"]
    width: int
    height: int
    dhash: str = ""  # 64-bit difference hash of the rendered page (identical scans differ in a few bits)


class Block(BaseModel):
    label: str | None = None
    prompt: str | None = None
    text: str = ""
    final: str | None = None


class PageReading(BaseModel):
    n: int
    blocks: list[Block] = []
    text: str = ""
    notes: str = ""


class QuestionResult(BaseModel):
    question_id: str
    page: int | None = None
    answer: str = ""
    final: str | None = None
    second_final: str | None = None
    status: ResultStatus = "unanswered"
    correct: bool | None = None
    points: float = 0
    max_points: float = 0
    criteria: dict[str, float] = {}
    feedback: str = ""
    errors: list[str] = []
    specifics: list[str] = []
    confidence: Confidence = "high"
    flags: list[str] = []
    override_points: float | None = None
    override_final: str | None = None
    comment: str = ""
    # What the grader said, kept so a corrected reading can be re-scored in code without a model call.
    model_points: float | None = None
    matches_key: bool | None = None
    model_feedback: str = ""
    model_confidence: Confidence = "high"


class Signal(BaseModel):
    code: str
    strength: float
    detail: dict = {}


class AiAnalysis(BaseModel):
    score: int = 0
    level: Literal["low", "some", "strong", "insufficient"] = "insufficient"
    words: int = 0
    signals: list[Signal] = []
    note: str = ""
    likelihood: int = 0  # the grader's own estimate (0–100), one of the signals


class Finding(BaseModel):
    code: str
    severity: Literal["info", "warn", "alert"]
    detail: dict = {}


class Forensics(BaseModel):
    kind: Literal["scanned", "typed", "mixed", "image"] = "scanned"
    sha256: str = ""
    metadata: dict[str, str] = {}
    xmp: dict[str, str] = {}
    file_id: str | None = None
    fonts: list[str] = []
    findings: list[Finding] = []


class Paper(BaseModel):
    id: str
    created_at: datetime
    filename: str
    source: SourceKind = "pdf"
    sha256: str = ""
    split_from: str | None = None  # the batch file this paper was cut from (its document IDs are the batch's)
    student_name: str = ""
    student_id: str = ""
    name_from: Literal["file", "paper", "professor"] = "file"
    status: PaperStatus = "queued"
    error: str | None = None
    failed_stage: Literal["reading", "grading"] | None = None
    pages: list[PageInfo] = []
    reading: list[PageReading] = []
    results: list[QuestionResult] = []
    summary: str = ""
    rubric_version: int = 0
    ai: AiAnalysis | None = None
    forensics: Forensics | None = None
    reviewed: bool = False
    note: str = ""
    updated_at: datetime | None = None

    def result(self, question_id: str) -> QuestionResult | None:
        return next((r for r in self.results if r.question_id == question_id), None)


class PaperRow(BaseModel):
    """A paper's line in assessment.json: everything the list views need, kept in step by the store."""
    id: str
    filename: str
    student_name: str = ""
    student_id: str = ""
    status: PaperStatus = "queued"
    error: str | None = None
    page_count: int = 0
    points: float | None = None
    max_points: float = 0
    grade: float | None = None
    ai_score: int | None = None
    ai_level: str | None = None
    ai_signals: list[str] = []     # the strongest AI signals (codes), for the lists
    findings: list[str] = []       # document findings worth showing (codes of warnings and alerts)
    copy_score: int | None = None
    copy_match: str | None = None
    alerts: int = 0
    review_flags: int = 0
    needs_review: bool = False
    reviewed: bool = False
    rubric_version: int = 0
    marks: dict[str, float] = {}   # question id → effective points (for the class statistics)
    picks: dict[str, str] = {}     # true/false and multiple choice: what was answered ("true", "β", "" = blank)
    created_at: datetime
    updated_at: datetime


# --- Class analysis ---------------------------------------------------------------------------------------------

class Evidence(BaseModel):
    code: str
    strength: float
    question_id: str | None = None
    detail: dict = {}


class SharedItem(BaseModel):
    """Something the side-by-side check found in both papers, in each paper's own words (checked in the text)."""
    question_id: str | None = None
    what: str
    a: str
    b: str
    rare: bool = False  # few other papers of the class have these words


class PairResult(BaseModel):
    a: str
    b: str
    score: int
    evidence: list[Evidence] = []
    verdict: Literal["likely_copied", "possibly", "independent", ""] = ""
    explanation: str = ""
    shared: list[SharedItem] = []


class Cluster(BaseModel):
    question_id: str
    kind: Literal["mistake", "detail"]
    label: str
    members: list[str]


class Analysis(BaseModel):
    status: Literal["idle", "running", "done", "failed"] = "idle"
    stale: bool = False
    computed_at: datetime | None = None
    error: str | None = None
    covered: list[str] = []  # the papers it analysed
    pairs: list[PairResult] = []
    clusters: list[Cluster] = []
    insights: str = ""
    recommendations: list[str] = []
    question_insights: dict[str, str] = {}


# --- Assessment -------------------------------------------------------------------------------------------------

class Assessment(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    title: str
    course: str = ""
    language: Language
    scale: Scale = 10
    instructions: str = ""
    paused: bool = False
    rubric: Rubric = Rubric()
    papers: list[PaperRow] = []
    analysis: Analysis = Analysis()

    def row(self, paper_id: str) -> PaperRow | None:
        return next((r for r in self.papers if r.id == paper_id), None)


class HistogramBin(BaseModel):
    start: float
    end: float
    count: int


class QuestionStats(BaseModel):
    question_id: str
    answered: int = 0
    graded: int = 0
    mean_pct: float | None = None
    correct_rate: float | None = None
    distribution: dict[str, int] = {}


class Stats(BaseModel):
    total: int = 0
    counts: dict[str, int] = {}
    graded: int = 0
    busy: bool = False
    needs_review: int = 0
    reviewed: int = 0
    flagged: int = 0
    mean: float | None = None
    median: float | None = None
    sd: float | None = None
    min: float | None = None
    max: float | None = None
    pass_rate: float | None = None
    histogram: list[HistogramBin] = []
    questions: list[QuestionStats] = []


class AssessmentView(Assessment):
    stats: Stats
    exam_chars: int = 0


class AssessmentSummary(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    title: str
    course: str
    language: Language
    scale: int
    rubric_status: str
    papers: int
    graded: int
    busy: bool
    paused: bool
    mean: float | None
    needs_review: int
    flagged: int
    histogram: list[int] = []  # papers per tenth of the scale, for the tile


# --- Requests ---------------------------------------------------------------------------------------------------

class AssessmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    course: str | None = Field(default=None, max_length=200)
    instructions: str | None = Field(default=None, max_length=6000)
    scale: Scale | None = None


class CriterionIn(BaseModel):
    id: str | None = None
    text: str = Field(min_length=1, max_length=600)
    points: float = Field(gt=0)


class QuestionIn(BaseModel):
    id: str | None = None
    label: str = Field(min_length=1, max_length=40)
    type: QuestionType
    prompt: str = Field(default="", max_length=2000)
    points: float = Field(gt=0, le=1000)
    options: list[str] = Field(default=[], max_length=12)
    answer: str = Field(default="", max_length=600)
    tolerance: float = Field(default=0, ge=0)
    model_answer: str = Field(default="", max_length=6000)
    criteria: list[CriterionIn] = Field(default=[], max_length=12)
    partial: bool = False
    key_from: Literal["exam", "lara", "professor"] = "professor"


class RubricUpdate(BaseModel):
    questions: list[QuestionIn] = Field(max_length=120)
    confirm: bool = False


class ResultOverride(BaseModel):
    override_points: float | None = Field(default=None, ge=0)
    override_final: str | None = Field(default=None, max_length=300)
    comment: str | None = Field(default=None, max_length=2000)
    clear_points: bool = False   # back to the suggested points
    clear_final: bool = False    # back to the reading


class PaperUpdate(BaseModel):
    student_name: str | None = Field(default=None, max_length=200)
    student_id: str | None = Field(default=None, max_length=100)
    reviewed: bool | None = None
    note: str | None = Field(default=None, max_length=4000)
    results: dict[str, ResultOverride] = {}


class ExportRequest(BaseModel):
    format: Literal["csv", "xlsx", "pdf"]
