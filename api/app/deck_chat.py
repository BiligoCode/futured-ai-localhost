"""The slides assistant: one model call that answers the professor and/or edits slides, as JSON (spec §6).

Edits carry the full new HTML of a slide, so writing text and changing formatting are the same operation; the
sanitiser and the language check decide whether a reply is acceptable, and an unacceptable one is retried once."""
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.deck_store import new_slide_id
from app.llm import LLM
from app.models import Deck, EditLog, Slide
from app.parsing import extract_json
from app.slides_html import PALETTE, sanitize_slide_html, slide_text, slide_title
from app.storyboard import check_language, language_name

MATERIAL_CHARS = 12_000
HISTORY_MESSAGES = 10
HISTORY_CHARS = 600
MAX_EDITS = 40
LANGUAGE_CHECK_MIN_LETTERS = 40
ATTEMPTS = 2

SYSTEM_PROMPT = """You are Lara, an assistant to a university professor who is writing lecture slides. You see \
the whole deck as numbered slides written in a small HTML subset. The professor chats with you to (1) ask \
questions or for ideas, (2) have you write or correct slide text, (3) have you change the formatting. One \
message may ask for several of these; do all of them.

Reply with only a JSON object:
{{"reply": "<what you say to the professor: plain text, short>",
 "edits": [
   {{"op": "replace", "slide": "<id>", "html": "<the full new html of that slide>"}},
   {{"op": "insert_after", "slide": "<id or null>", "html": "<html of the new slide>"}},
   {{"op": "delete", "slide": "<id>"}},
   {{"op": "move", "slide": "<id>", "after": "<id or null>"}}
 ]}}
"slide": null in insert_after/move means the beginning of the deck. Edits are applied in order; several \
insert_after edits naming the same slide are placed one after another in the order given.

Slide HTML rules:
- Allowed tags: h1 h2 p ul ol li strong em u mark br span. Nothing else (no div, no tables, no images, no links).
- Alignment: style="text-align: center" (or left/right) on h1, h2, p or li.
- Colour: <span style="color: #1b6f8c">…</span>. Palette: {palette}.
- Size: <span style="font-size: 34px">…</span>. Body text is 26px; use 20 for small, 34 for large, 44 for extra large.
- At most one h1 per slide (its title); h2 for sub-headings; <mark> to highlight.
- A slide is 1280×720 px with 64 px padding: about 7 lines of body text, or a title and about 5 lines. Split \
content over several slides rather than overflowing one.
- Keep everything the professor did not ask to change exactly as it is (same text, same formatting). Never touch \
slides the professor did not ask about.
- Mathematics in Unicode (x², Σ, √, ≤); there is no LaTeX.

The slides are written in {language}: all slide text you write must be in {language}. The professor may write to \
you in any language; answer in the language of the professor's message.
When the professor only asks a question, "edits" is an empty list. When you edit, say briefly in "reply" what you \
changed. Never put the JSON inside the reply text."""


class DeckChatError(RuntimeError):
    pass


class _Edit(BaseModel):
    op: Literal["replace", "insert_after", "delete", "move"]
    slide: str | None = None
    html: str | None = None
    after: str | None = None


class _Reply(BaseModel):
    reply: str = ""
    edits: list[_Edit] = Field(default_factory=list, max_length=MAX_EDITS)


_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)


def build_system_prompt(deck: Deck) -> str:
    return SYSTEM_PROMPT.format(language=language_name(deck.language), palette=" ".join(PALETTE))


def _history(deck: Deck) -> str:
    index = {s.id: i + 1 for i, s in enumerate(deck.slides)}
    lines = []
    for m in deck.chat[-HISTORY_MESSAGES:]:
        text = m.content[:HISTORY_CHARS]
        if m.role == "user":
            lines.append(f"Professor: {text}")
        else:
            changed = ", ".join(str(index[e.slide_id]) if e.slide_id in index else (e.title or "?") for e in m.edits)
            lines.append(f"Lara: {text}" + (f" (changed slides {changed})" if changed else ""))
    return "\n".join(lines)


def build_user_message(deck: Deck, material: str, message: str, *, slide_id: str | None,
                       selection: str | None) -> str:
    parts = [f"Deck title: {deck.title}"]
    if material.strip():
        parts.append(f"Course material (excerpt):\n<<<\n{material[:MATERIAL_CHARS]}\n>>>")
    parts.append("Slides:\n" + "\n".join(f"[{s.id}] {s.html}" for s in deck.slides))
    if deck.chat:
        parts.append("Earlier in this conversation:\n" + _history(deck))
    if slide_id:
        context = f"The professor is looking at slide [{slide_id}]."
        if selection:
            context += f'\nSelected text on that slide: "{selection}"'
        parts.append(context)
    parts.append(f"Professor: {message}")
    return "\n\n".join(parts)


def apply_edits(slides: list[Slide], edits: list[_Edit]) -> tuple[list[Slide], list[EditLog]]:
    """Apply the model's edits to a copy of the slides. Raises ValueError for anything the deck cannot take."""
    out = [s.model_copy() for s in slides]
    log: list[EditLog] = []

    def index_of(slide_id: str | None) -> int:
        for i, s in enumerate(out):
            if s.id == slide_id:
                return i
        raise ValueError(f"slide {slide_id!r} does not exist")

    def clean(html: str | None) -> str:
        cleaned = sanitize_slide_html(html or "")
        if not slide_text(cleaned).strip():
            raise ValueError("a slide must contain some text")
        return cleaned

    last_insert: tuple[str | None, int] | None = None  # (anchor, index of the last slide inserted after it)
    for e in edits:
        if e.op == "replace":
            i = index_of(e.slide)
            out[i] = out[i].model_copy(update={"html": clean(e.html)})
            log.append(EditLog(op="replace", slide_id=out[i].id, title=slide_title(out[i].html)))
        elif e.op == "insert_after":
            if last_insert and last_insert[0] == e.slide:
                at = last_insert[1] + 1
            else:
                at = index_of(e.slide) + 1 if e.slide is not None else 0
            slide = Slide(id=new_slide_id(), html=clean(e.html))
            out.insert(at, slide)
            last_insert = (e.slide, at)
            log.append(EditLog(op="insert_after", slide_id=slide.id, title=slide_title(slide.html)))
            continue
        elif e.op == "delete":
            if len(out) == 1:
                raise ValueError("the deck must keep at least one slide")
            i = index_of(e.slide)
            log.append(EditLog(op="delete", slide_id=out[i].id, title=slide_title(out[i].html)))
            del out[i]
        elif e.op == "move":
            if e.slide == e.after:
                raise ValueError("a slide cannot be moved after itself")
            slide = out.pop(index_of(e.slide))
            at = index_of(e.after) + 1 if e.after is not None else 0
            out.insert(at, slide)
            log.append(EditLog(op="move", slide_id=slide.id, title=slide_title(slide.html)))
        last_insert = None
    return out, log


def _check_language(slides: list[Slide], log: list[EditLog], language: str) -> None:
    written = {e.slide_id for e in log if e.op in ("replace", "insert_after")}
    texts = [slide_text(s.html) for s in slides if s.id in written]
    if len(_LETTERS.findall(" ".join(texts))) >= LANGUAGE_CHECK_MIN_LETTERS:
        check_language(texts, language)


def run_chat(llm: LLM, deck: Deck, material: str, message: str, *, slide_id: str | None,
             selection: str | None) -> tuple[str, list[Slide], list[EditLog]]:
    system = build_system_prompt(deck)
    messages = [{"role": "user", "content": build_user_message(deck, material, message, slide_id=slide_id,
                                                                 selection=selection)}]
    error = ""
    for _ in range(ATTEMPTS):
        reply = llm(system, messages)
        try:
            parsed = _Reply.model_validate(extract_json(reply))
            slides, log = apply_edits(deck.slides, parsed.edits)
            _check_language(slides, log, deck.language)
            return parsed.reply.strip(), slides, log
        except (ValueError, ValidationError) as exc:
            error = str(exc)
            messages = messages + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"Your previous reply was not valid: {error}. Reply with only the JSON."},
            ]
    raise DeckChatError(f"Could not apply the assistant's reply: {error}")
