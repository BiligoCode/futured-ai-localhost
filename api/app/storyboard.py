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

SYSTEM_PROMPT = """You are an expert instructional designer helping a university professor.
You turn a concept from their course into one animated explanation video, planned as a sequence of scenes.

Rules:
- The whole video must last {label}: use {min_scenes} to {max_scenes} scenes and {min_words} to {max_words} \
words of narration in total.
- Write every "title", "visual" and "narration" in {language}.
- "visual" describes concretely what is shown and animated on screen (shapes, graphs, equations, arrows), \
including where things are placed, so an animator can build it without guessing.
- "narration" is what the narrator says during that scene.
- Scenes follow each other as one continuous explanation, not as separate videos.
- Reuse the notation, terminology and examples from the professor's course material.
- Follow the requested style and tone.
- Respond with only JSON in this exact shape:
{{"title": "<short title>", "scenes": [{{"title": "...", "visual": "...", "narration": "..."}}]}}"""


class StoryboardError(RuntimeError):
    pass


class _Storyboard(BaseModel):
    title: str = Field(min_length=1)
    scenes: list[SceneDraft] = Field(min_length=1, max_length=14)


def language_name(language: Language) -> str:
    return LANGUAGE_NAMES[language]


def build_system_prompt(language: Language, duration: DurationRange) -> str:
    d = DURATIONS[duration]
    return SYSTEM_PROMPT.format(language=language_name(language), label=d["label"],
                                min_scenes=d["scenes"][0], max_scenes=d["scenes"][1],
                                min_words=d["words"][0], max_words=d["words"][1])


def generate_storyboard(llm: LLM, *, material: str, concept: str, style: str, duration: DurationRange,
                        language: Language) -> tuple[str, list[SceneDraft]]:
    system = build_system_prompt(language, duration)
    user = (
        f"Concept to explain: {concept}\n"
        f"Style and tone: {style or 'clear and visual, friendly and precise'}\n"
        f"Video length: {DURATIONS[duration]['label']}\n\n"
        f"Course material:\n<<<\n{material}\n>>>"
    )
    messages = [{"role": "user", "content": user}]
    error = ""
    for _ in range(2):
        reply = llm(system, messages)
        try:
            board = _Storyboard.model_validate(extract_json(reply))
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
