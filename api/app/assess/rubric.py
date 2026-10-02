"""The rubric: drafting it with the model (design §6.5), normalising the professor's edits, checking it is gradable.

A key the model worked out itself is marked `key_from="lara"`; it stays flagged on every paper until the professor
confirms or changes it."""
import re
import uuid

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.assess.answers import parse_choices, parse_numbers, parse_true_false
from app.assess.models import Criterion, Question, QuestionIn
from app.assess.scoring import round_points
from app.llm import LLM, VisionLLM
from app.parsing import extract_json
from app.storyboard import language_name

ATTEMPTS = 2
EXAM_CHARS = 30_000
PAPER_CHARS = 9_000
DEFAULT_POINTS = {"true_false": 1.0, "multiple_choice": 1.0, "numeric": 2.0, "short": 2.0, "open": 5.0}
TYPE_ALIASES = {
    "true_false": "true_false", "truefalse": "true_false", "tf": "true_false", "true/false": "true_false",
    "boolean": "true_false", "σωστο_λαθοσ": "true_false",
    "multiple_choice": "multiple_choice", "multiplechoice": "multiple_choice", "mcq": "multiple_choice",
    "mc": "multiple_choice", "choice": "multiple_choice", "multiple-choice": "multiple_choice",
    "numeric": "numeric", "number": "numeric", "numerical": "numeric", "calculation": "numeric",
    "short": "short", "short_answer": "short", "shortanswer": "short", "fill_in": "short", "fill-in": "short",
    "open": "open", "essay": "open", "open_ended": "open", "open-ended": "open", "long": "open", "proof": "open",
    "problem": "open", "explanation": "open",
}

DRAFT_SYSTEM = """You prepare grading rubrics for a university professor. You are careful and exact: the rubric \
decides students' marks. Reply with only JSON."""

SCHEMA = """{{"questions": [{{
   "label": "<the question's number/label exactly as printed: '1', '2.β', 'Θέμα Α1', 'A2(iii)'>",
   "type": "true_false | multiple_choice | numeric | short | open",
   "prompt": "<the question text, in its original language (at most 400 characters)>",
   "points": <marks for this question as printed, or null if the paper does not say>,
   "options": ["<for multiple_choice: each option with its label as printed, e.g. 'β) O(n log n)'>"],
   "answer": "<the key: true_false → 'true' or 'false'; multiple_choice → the correct option label(s) as printed, e.g. 'β' or 'α,γ'; numeric → the number; short → the expected answer, alternatives separated by ' | '; open → ''>",
   "tolerance": <numeric: the acceptable absolute error, 0 for exact>,
   "model_answer": "<open (and numeric/short when working matters): a concise model solution, in {language}>",
   "criteria": [{{"text": "<one thing a full answer must contain, in {language}>", "points": <marks>}}],
   "partial": <true when part marks for correct working make sense (numeric/short), else false>,
   "key_from": "<'exam' if the key is given on the paper you were shown, 'lara' if you worked it out yourself>"}}],
 "note": "<in {language}, for the professor: anything to check — keys you worked out yourself, unclear marks, missing points>"}}"""

RULES = """Rules:
- One entry per item that receives its own marks: split "1. α) … β) …" into 1.α and 1.β when they are marked \
separately. Keep the order of the paper.
- Types: true_false for Σωστό/Λάθος or True/False items; multiple_choice when options are listed; numeric when the \
answer is a single number; short when the answer is a word, formula or short phrase that can be checked exactly; \
open for explanations, proofs, derivations, code, essays.
- Points: use the marks printed on the paper. If none are printed, use null.
- Keys: if the paper gives the answers or solutions, copy them (key_from "exam"). Otherwise solve every question \
yourself, carefully and step by step in your head, and give the key (key_from "lara"); check each value twice.
- Open questions: 2 to 5 criteria whose points add up to the question's points (if points are null, make the \
criteria add up to 5). Criteria name concrete content (a definition, a step, a result), not vague qualities.
- Copy question texts and option labels exactly; write model answers, criteria and the note in {language}."""


class RubricError(RuntimeError):
    pass


class _Criterion(BaseModel):
    text: str = ""
    points: float | None = None

    @field_validator("text", mode="before")
    @classmethod
    def _str(cls, v):
        return "" if v is None else str(v)

    @field_validator("points", mode="before")
    @classmethod
    def _num(cls, v):
        if isinstance(v, str):
            nums = parse_numbers(v)
            return nums[0] if nums else None
        return v


class _Question(BaseModel):
    label: str = ""
    type: str = "open"
    prompt: str = ""
    points: float | None = None
    options: list[str] = Field(default_factory=list)
    answer: str = ""
    tolerance: float | None = 0
    model_answer: str = ""
    criteria: list[_Criterion] = Field(default_factory=list)
    partial: bool = False
    key_from: str = "lara"

    @field_validator("label", "prompt", "answer", "model_answer", "type", "key_from", mode="before")
    @classmethod
    def _str(cls, v):
        if v is None:
            return ""
        if isinstance(v, list):
            return ",".join(str(x) for x in v)
        return str(v)

    @field_validator("points", "tolerance", mode="before")
    @classmethod
    def _num(cls, v):
        if v in (None, "", "null"):
            return None
        if isinstance(v, str):
            nums = parse_numbers(v)
            return nums[0] if nums else None
        return v

    @field_validator("options", mode="before")
    @classmethod
    def _opts(cls, v):
        if isinstance(v, dict):
            return [f"{k}) {t}" for k, t in v.items()]
        return [str(x) for x in (v or [])]

    @field_validator("partial", mode="before")
    @classmethod
    def _bool(cls, v):
        return bool(v) and str(v).lower() not in ("false", "0", "no")


class _Draft(BaseModel):
    questions: list[_Question] = Field(min_length=1, max_length=120)
    note: str = ""


def new_question_id() -> str:
    return uuid.uuid4().hex[:6]


def _type(value: str) -> str:
    key = re.sub(r"[\s]+", "_", value.strip().lower())
    return TYPE_ALIASES.get(key, "open")


def scale_criteria(criteria: list[Criterion], points: float) -> list[Criterion]:
    """Make criteria add up to the question's points exactly (in quarter points)."""
    total = sum(c.points for c in criteria)
    if not criteria or total <= 0 or abs(total - points) < 1e-6:
        return criteria
    out = [c.model_copy(update={"points": max(0.25, round_points(c.points * points / total))}) for c in criteria]
    diff = round_points(points - sum(c.points for c in out))
    if diff:
        last = max(range(len(out)), key=lambda i: out[i].points)
        out[last] = out[last].model_copy(update={"points": max(0.25, out[last].points + diff)})
    return out


def _canonical_key(qtype: str, answer: str) -> str:
    answer = answer.strip()
    if qtype == "true_false":
        value = parse_true_false(answer)
        return "" if value is None else ("true" if value else "false")
    return answer


def _from_draft(d: _Question) -> Question:
    qtype = _type(d.type)
    points = d.points if d.points and d.points > 0 else DEFAULT_POINTS[qtype]
    criteria = [Criterion(id=f"c{i + 1}", text=c.text.strip()[:600], points=c.points if c.points and c.points > 0 else 1.0)
                for i, c in enumerate(d.criteria) if c.text.strip()][:8]
    if qtype == "open":
        criteria = scale_criteria(criteria, points)
    else:
        criteria = []
    return Question(
        id=new_question_id(), label=(d.label.strip() or "?")[:40], type=qtype, prompt=d.prompt.strip()[:2000],
        points=round_points(points) or 0.25, options=[o.strip()[:300] for o in d.options if o.strip()][:12] if qtype == "multiple_choice" else [],
        answer=_canonical_key(qtype, d.answer)[:600] if qtype != "open" else "",
        tolerance=max(0.0, d.tolerance or 0.0) if qtype == "numeric" else 0.0,
        model_answer=d.model_answer.strip()[:6000], criteria=criteria,
        partial=d.partial and qtype in ("numeric", "short"),
        key_from="exam" if d.key_from.strip().lower() == "exam" else "lara",
    )


def parse_draft(reply: str) -> tuple[list[Question], str]:
    draft = _Draft.model_validate(extract_json(reply))
    questions = [_from_draft(q) for q in draft.questions]
    seen: dict[str, int] = {}
    for q in questions:  # labels must be unique for the grader to address questions
        if q.label in seen:
            seen[q.label] += 1
            q.label = f"{q.label} ({seen[q.label]})"
        else:
            seen[q.label] = 1
    return questions, draft.note.strip()[:2000]


def _run(call, prompt: str) -> tuple[list[Question], str]:
    error = ""
    for attempt in range(ATTEMPTS):
        text = prompt if attempt == 0 else prompt + f"\n\nYour previous reply was not valid: {error}. Reply with only the JSON."
        reply = call(text)
        try:
            return parse_draft(reply)
        except (ValueError, ValidationError) as exc:
            error = str(exc)[:400]
    raise RubricError(f"Could not draft a rubric: {error}")


def _instructions(language: str) -> str:
    name = language_name(language)
    return "Reply with this JSON:\n" + SCHEMA.format(language=name) + "\n\n" + RULES.format(language=name)


def draft_from_text(llm: LLM, exam_text: str, language: str, *, title: str = "") -> tuple[list[Question], str]:
    prompt = (f"Exam: {title}\n\nThe exam paper (and the answer key, if the professor included it):\n<<<\n"
              f"{exam_text[:EXAM_CHARS]}\n>>>\n\n" + _instructions(language))
    return _run(lambda p: llm(DRAFT_SYSTEM, [{"role": "user", "content": p}]), prompt)


def draft_from_images(vision: VisionLLM, images: list[bytes], language: str, *, title: str = "",
                      exam_text: str = "") -> tuple[list[Question], str]:
    extra = f"\n\nText the professor typed in addition:\n<<<\n{exam_text[:EXAM_CHARS]}\n>>>" if exam_text.strip() else ""
    prompt = (f"Exam: {title}\n\nThe images are the pages of the exam paper (and possibly its answer key).{extra}\n\n"
              + _instructions(language))
    return _run(lambda p: vision(DRAFT_SYSTEM, p, images[:12]), prompt)


def draft_from_papers(llm: LLM, transcripts: list[str], language: str, *, title: str = "") -> tuple[list[Question], str]:
    papers = "\n\n".join(f"=== Paper {i + 1} ===\n{t[:PAPER_CHARS]}" for i, t in enumerate(transcripts[:3]))
    prompt = (f"Exam: {title}\n\nThe professor gave no exam paper. Below are transcriptions of {len(transcripts[:3])} "
              "students' papers for this exam. Printed question texts appear in each block's prompt and the labels in "
              "[brackets]. Work out the list of questions from them. The students' answers may be wrong: never take a "
              "key from them — solve each question yourself (key_from \"lara\").\n\n" + papers + "\n\n" + _instructions(language))
    return _run(lambda p: llm(DRAFT_SYSTEM, [{"role": "user", "content": p}]), prompt)


# --- The professor's rubric -------------------------------------------------------------------------------------

def from_input(items: list[QuestionIn], existing: list[Question]) -> list[Question]:
    """The rubric as the professor saved it: known ids kept, new questions get ids, criteria renumbered."""
    known = {q.id for q in existing}
    out: list[Question] = []
    used: set[str] = set()
    for item in items:
        qid = item.id if item.id in known and item.id not in used else new_question_id()
        used.add(qid)
        criteria = [Criterion(id=f"c{i + 1}", text=c.text.strip(), points=c.points)
                    for i, c in enumerate(item.criteria)] if item.type == "open" else []
        out.append(Question(
            id=qid, label=item.label.strip(), type=item.type, prompt=item.prompt.strip(), points=item.points,
            options=[o.strip() for o in item.options if o.strip()] if item.type == "multiple_choice" else [],
            answer=_canonical_key(item.type, item.answer) if item.type != "open" else "",
            tolerance=item.tolerance if item.type == "numeric" else 0.0, model_answer=item.model_answer.strip(),
            criteria=criteria, partial=item.partial and item.type in ("numeric", "short"), key_from=item.key_from,
        ))
    return out


def check_gradable(questions: list[Question]) -> str | None:
    """Why this rubric cannot be used for grading yet (English, translated by prefix), or None."""
    if not questions:
        return "Add at least one question before grading"
    labels: set[str] = set()
    for q in questions:
        if q.label in labels:
            return f"Two questions have the same label: {q.label}"
        labels.add(q.label)
        if q.type == "true_false" and parse_true_false(q.answer) is None:
            return f"Choose whether the answer is true or false for question: {q.label}"
        if q.type == "multiple_choice" and parse_choices(q.answer, q.options, n_options=max(len(q.options), 8)) is None:
            return f"Give the correct option for question: {q.label}"
        if q.type == "numeric" and not parse_numbers(q.answer):
            return f"Give the correct number for question: {q.label}"
        if q.type == "short" and not q.answer.strip():
            return f"Give the expected answer for question: {q.label}"
        if q.type == "open" and q.criteria and abs(sum(c.points for c in q.criteria) - q.points) > 0.01:
            return f"The criteria do not add up to the points of question: {q.label}"
    return None


_KEY_FIELDS = ("type", "points", "answer", "options", "tolerance", "partial", "model_answer")


def changed_questions(old: list[Question], new: list[Question]) -> set[str]:
    """Questions whose marking changed (new ones included): their marks and the professor's overrides are redone."""
    before = {q.id: q for q in old}
    changed = set()
    for q in new:
        p = before.get(q.id)
        if p is None or any(getattr(p, f) != getattr(q, f) for f in _KEY_FIELDS) or \
                [(c.text, c.points) for c in p.criteria] != [(c.text, c.points) for c in q.criteria]:
            changed.add(q.id)
    return changed
