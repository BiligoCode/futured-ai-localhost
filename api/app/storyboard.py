import re

from pydantic import BaseModel, Field, ValidationError

from app.llm import LLM
from app.models import DurationRange, Language, SceneDraft
from app.parsing import extract_json

LANGUAGE_NAMES = {"el": "Greek", "en": "English"}

# Narration is spoken at roughly 150 words per minute, so a duration range sets the scene count and word budget.
DURATIONS: dict[DurationRange, dict] = {
    "short": {"label": "under 1 minute", "scenes": (3, 4), "words": (80, 140)},
    "medium": {"label": "1 to 3 minutes", "scenes": (4, 7), "words": (150, 420)},
    "long": {"label": "3 to 5 minutes", "scenes": (7, 12), "words": (450, 720)},
}

SYSTEM_PROMPT = """You are an expert instructional designer and animator helping a university professor.
You plan ONE animated video that explains exactly one concept, as a sequence of scenes.

Language: write every "title", "visual" and "narration" in {language}. This holds whatever language the concept, \
the style notes or the course material are written in: translate them. Keep standard notation, formulas and code \
identifiers as they are.

Focus and precision:
- Explain the requested concept itself, thoroughly and precisely. Do not spend scenes on history, people, \
etymology, motivation speeches, lists of applications, or general overviews of the wider field. Mention \
background only where the concept cannot be understood without it, and keep it to a sentence.
- Build the explanation on one concrete worked example, taken from the course material when it has one (its \
numbers, notation, definitions, recurrences, pseudocode). Otherwise construct one small enough to show completely. \
Carry the same example through the scenes so the student watches the method run step by step to the result.
- Get the example right: check every value, step and result you show (e.g. that each sum uses only the given \
coins, that each table cell follows the recurrence). The professor will show this to students.
- Use everything in the material that concerns this concept: definitions, the key idea, the recurrence or \
formula, how the algorithm or proof proceeds, correctness or invariants, complexity, edge cases and typical \
mistakes. Leave out what does not concern it.
- This is a visual explanation. Every scene must show something changing on screen that carries the idea \
(values filling a table, pointers moving, a graph being built, terms of an equation transforming), and the \
narration explains what the viewer sees at that moment. No text-only scenes.

Rules:
- The whole video must last {label}: use {min_scenes} to {max_scenes} scenes and {min_words} to {max_words} \
words of narration in total.
- "visual": exactly what is on screen and how it moves, with the actual values, labels and positions (what is \
where, what gets highlighted, in what order), so an animator can build it without guessing. The bottom strip of \
the screen stays empty: it is reserved for captions.
- "narration": what the narrator says during that scene, following the visual step by step.
- Scenes follow each other as one continuous explanation, not as separate videos.
- Follow the requested style and tone.
- Respond with only JSON in this exact shape:
{{"title": "<short title>", "scenes": [{{"title": "...", "visual": "...", "narration": "..."}}]}}"""


NO_MATERIAL = """Course material: none was given. Teach the concept from your own knowledge, the way a careful \
university lecturer would: use the standard definitions, notation and terminology of the field, pick the canonical \
worked example a textbook would use, and cover what the rules ask of the material (definitions, the key idea, how \
the method proceeds, correctness, complexity, edge cases, typical mistakes). Before writing, think the concept and \
the example through step by step and check every value. State only what you are sure is correct; do not invent \
citations or course-specific details."""


class StoryboardError(RuntimeError):
    pass


class _Storyboard(BaseModel):
    title: str = Field(min_length=1)
    scenes: list[SceneDraft] = Field(min_length=1, max_length=14)


def language_name(language: Language) -> str:
    return LANGUAGE_NAMES[language]


_GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
_LATIN = re.compile(r"[A-Za-z]")
# Letters of other scripts (Cyrillic, Armenian, Hebrew, Arabic, CJK, ...) that models sometimes slip in.
_OTHER_SCRIPT = re.compile(r"[\u0400-\u052f\u0530-\u08ff\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def greek_share(texts: list[str]) -> float:
    joined = " ".join(texts)
    greek, latin = len(_GREEK.findall(joined)), len(_LATIN.findall(joined))
    return greek / (greek + latin) if greek + latin else 0.0


def check_language(texts: list[str], language: Language) -> None:
    """The selected language is the only source of truth: reject text written in the other one.

    Greek text may contain Latin notation (O(n), dp[i], code), so it only has to be mostly Greek."""
    foreign = sorted({w for t in texts for w in t.split() if _OTHER_SCRIPT.search(w)})
    if foreign:
        raise ValueError(f"these words are in neither {language_name(language)} nor standard notation: "
                         f"{', '.join(foreign[:8])}; write them in {language_name(language)}")
    share = greek_share(texts)
    if language == "el" and share < 0.6:
        raise ValueError("the text must be written in Greek (it is mostly in another language); translate it")
    if language == "en" and share > 0.2:
        raise ValueError("the text must be written in English (it contains Greek); translate it")


def build_system_prompt(language: Language, duration: DurationRange) -> str:
    d = DURATIONS[duration]
    return SYSTEM_PROMPT.format(language=language_name(language), label=d["label"],
                                min_scenes=d["scenes"][0], max_scenes=d["scenes"][1],
                                min_words=d["words"][0], max_words=d["words"][1])


def generate_storyboard(llm: LLM, *, material: str, concept: str, style: str, duration: DurationRange,
                        language: Language) -> tuple[str, list[SceneDraft]]:
    system = build_system_prompt(language, duration)
    user = (
        f"Concept to explain (the professor may have typed it in any language): {concept}\n"
        f"Write the video in: {language_name(language)}\n"
        f"Style and tone: {style or 'clear and visual, friendly and precise'}\n"
        f"Video length: {DURATIONS[duration]['label']}\n\n"
        + (f"Course material:\n<<<\n{material}\n>>>" if material.strip() else NO_MATERIAL)
    )
    messages = [{"role": "user", "content": user}]
    error = ""
    for _ in range(3):
        reply = llm(system, messages)
        try:
            board = _Storyboard.model_validate(extract_json(reply))
            check_language([board.title, *(t for sc in board.scenes for t in (sc.title, sc.narration))], language)
            return board.title, [SceneDraft(title=s.title, visual=s.visual, narration=s.narration)
                                 for s in board.scenes]
        except (ValueError, ValidationError) as exc:
            error = str(exc)
            messages = messages + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"Your previous reply was not valid: {error}. "
                                            "Reply with only the JSON."},
            ]
    raise StoryboardError(f"Could not generate a valid storyboard: {error}")
