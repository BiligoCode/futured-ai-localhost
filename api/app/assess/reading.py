"""Reading scanned pages with a vision model (design §6.1) — transcription only, never judgement.

The reader never sees the answer key, so an ambiguous mark is reported as written (with [?]) instead of as what the
key expects. The transcript is what the grader reads, what the professor checks against the scan, and what the
similarity analysis compares."""
import re
from typing import Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.assess.answers import normalize_text
from app.assess.models import Block, PageReading
from app.llm import VisionLLM
from app.parsing import extract_json

ATTEMPTS = 2
MAX_BLOCK_CHARS = 6000
_WORD = re.compile(r"[^\W_]+", re.UNICODE)

READ_SYSTEM = """You transcribe scanned university exam papers for a professor who grades them. You copy exactly \
what is on the page; you never solve, judge, correct or complete anything. Reply with only JSON."""

READ_PROMPT = """This is page {page} of {pages} of one student's exam paper.

Transcribe it as JSON:
{{"student_name": "<the student's name if written on this page, else null>",
 "student_id": "<the student/registration number (e.g. ΑΜ, ID) if written on this page, else null>",
 "blocks": [{{"label": "<the question number/label printed or written next to the answer, e.g. '3', '2.β', 'Θέμα Α1'; null if none>",
             "prompt": "<the question text PRINTED on the page (typed, not handwritten), at most 200 characters; null when the question is not printed there>",
             "text": "<everything the STUDENT wrote for it, in reading order>",
             "final": "<the answer the student marked or stated as final (circled, boxed, underlined, after '=', 'Answer:'); null if none>"}}],
 "notes": "<anything the grader must know: illegible words, overwritten digits, two possible readings, drawings, arrows, pages out of order; empty if none>"}}

Rules:
- Copy the student's own words exactly, in the language they wrote, with their spelling mistakes. Never fix, \
translate, summarise, or add anything.
- Crossed-out text: write it as ~~crossed text~~. Characters you cannot read: [?]. If a digit or letter could be \
two things, keep your best reading in the text and describe both in "notes".
- Circled, ticked or underlined options: "(circled: β)", "(ticked: Σωστό)". True/false written as Σ/Λ or T/F: \
copy the letter.
- Mathematics in plain Unicode or ASCII: x², √, ≤, ≠, a/b, O(n log n). Code exactly as written.
- Drawings, graphs, trees, tables: describe them in [figure: …] with the values shown.
- Printed question text goes only in "prompt", never in "text". Everything handwritten — the whole answer, from its \
first word — goes in "text", never in "prompt". A block per answered question, in page order.
- A page without anything the student wrote: "blocks": [].
- Do not repeat the printed instructions or headers."""


class ReadingError(RuntimeError):
    pass


class _Block(BaseModel):
    label: str | None = None
    prompt: str | None = None
    text: str = ""
    final: str | None = None

    @field_validator("label", "prompt", "final", mode="before")
    @classmethod
    def _text(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @field_validator("text", mode="before")
    @classmethod
    def _body(cls, v):
        return "" if v is None else str(v)


class _Page(BaseModel):
    student_name: str | None = None
    student_id: str | None = None
    blocks: list[_Block] = Field(default_factory=list)
    notes: str = ""

    @field_validator("blocks", mode="before")
    @classmethod
    def _blocks(cls, v):
        # Models sometimes answer with a bare list of strings for a page with free writing.
        if isinstance(v, list):
            return [{"text": b} if isinstance(b, str) else b for b in v]
        return v or []

    @field_validator("student_name", "student_id", mode="before")
    @classmethod
    def _who(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return None if v.lower() in {"", "null", "none", "n/a", "-"} else v[:120]

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, v):
        if isinstance(v, list):
            return "; ".join(str(x) for x in v)
        return "" if v is None else str(v)


def _words(text: str) -> list[str]:
    return _WORD.findall(normalize_text(text))


def _settle(prompt: str | None, text: str) -> tuple[str | None, str]:
    """(prompt, text). A printed question never begins or ends with the student's words: when the reader filed an
    answer under "prompt" and repeated only its first or last sentence as "text", the whole of it is the student's."""
    p, t = _words(prompt or ""), _words(text)
    if prompt and len(t) >= 3 and len(p) > len(t) and (p[:len(t)] == t or p[-len(t):] == t):
        return None, prompt
    return prompt, text


def parse_page(reply: str, n: int) -> tuple[PageReading, str | None, str | None]:
    data = extract_json(reply)
    if isinstance(data, list):
        data = {"blocks": data}
    page = _Page.model_validate(data)
    blocks = []
    for b in page.blocks:
        prompt, text = _settle(b.prompt, b.text)
        # A block with only "printed" text is kept: the reader sometimes files the whole handwritten answer there,
        # and whether it is the student's is decided against the exam when the paper is graded (reading_text).
        if text.strip() or b.final or (prompt or "").strip():
            blocks.append(Block(label=b.label, prompt=(prompt or None) and prompt[:300], text=text[:MAX_BLOCK_CHARS],
                                final=b.final and b.final[:300]))
    return PageReading(n=n, blocks=blocks, notes=page.notes[:1500]), page.student_name, page.student_id


def read_page(vision: VisionLLM, image: bytes, n: int, pages: int) -> tuple[PageReading, str | None, str | None]:
    """Transcribe one page. Raises ReadingError if the model never returns usable JSON."""
    prompt = READ_PROMPT.format(page=n, pages=pages)
    error = ""
    for attempt in range(ATTEMPTS):
        text = prompt if attempt == 0 else prompt + f"\n\nYour previous reply was not valid JSON ({error}). Reply with only the JSON object."
        reply = vision(READ_SYSTEM, text, [image])
        try:
            return parse_page(reply, n)
        except (ValueError, ValidationError) as exc:
            error = str(exc)[:300]
    raise ReadingError(f"Could not read page {n}: {error}")


def printed_check(reference: str) -> Callable[[str], bool] | None:
    """Whether what the reader filed as a block's printed question is in the exam or the questions (most of its
    three-word sequences are) — None when there is nothing to check against."""
    words = _words(reference)
    vocabulary, grams = set(words), set(zip(words, words[1:], words[2:]))
    if not grams:
        return None

    def printed(prompt: str) -> bool:
        w = _words(prompt)
        own = list(zip(w, w[1:], w[2:]))
        if not own:  # a word or two: printed only if the exam has them
            return all(x in vocabulary for x in w)
        return sum(g in grams for g in own) >= 0.5 * len(own)
    return printed


def _students(b: Block, printed: Callable[[str], bool] | None) -> bool:
    """Whether a block's "printed question" is really the student's writing."""
    if not b.text.strip():
        # The reader lists answered questions only: a block with nothing else is an answer filed in the wrong field,
        # unless it is a printed question found in the exam (a word or two is never a printed question).
        return printed is None or len(_words(b.prompt or "")) < 3 or not printed(b.prompt or "")
    return printed is not None and not printed(b.prompt or "")


def reading_text(reading: list[PageReading], methods: dict[int, str] | None = None, *,
                 printed: Callable[[str], bool] | None = None, show_printed: bool = False) -> str:
    """The whole paper as the grader reads it: page by page, blocks as `[label] text ⟶ final`. A block's "printed
    question" that `printed` does not find in the exam is the student's own writing, so it is kept as part of the
    answer — and so is one with no other text when there is no exam to check against (the reader lists answered
    questions only). Real printed text is left out, or shown as `(printed: …)` with `show_printed`."""
    parts = []
    for page in reading:
        lines = [f"--- page {page.n} ---"]
        if page.text:
            lines.append(page.text)
        for b in page.blocks:
            head = f"[{b.label}] " if b.label else ""
            body = b.text
            if b.prompt and show_printed:
                head += f"(printed: {b.prompt}) "
            elif b.prompt and _students(b, printed):
                body = f"{b.prompt} {b.text}".strip()
            tail = f" ⟶ final: {b.final}" if b.final else ""
            lines.append(f"{head}{body}{tail}".strip())
        if page.notes:
            lines.append(f"(reader's notes: {page.notes})")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def student_identity(readings: list[tuple[str | None, str | None]]) -> tuple[str, str]:
    """The first name and the first ID found on the pages (they are usually on page 1)."""
    name = next((n for n, _ in readings if n), "")
    sid = next((s for _, s in readings if s), "")
    return name, sid
