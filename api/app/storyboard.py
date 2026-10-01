from pydantic import BaseModel, Field, ValidationError

from app.llm import LLM
from app.models import Language, SceneDraft
from app.parsing import extract_json

LANGUAGE_NAMES = {"el": "Greek", "en": "English"}

SYSTEM_PROMPT = """You are an expert instructional designer helping a university professor.
You turn a concept from their course into a short animated explanation made of 4 to 6 scenes.

Rules:
- Write every "title", "visual" and "narration" in {language}.
- "visual" describes concretely what is shown and animated on screen (shapes, graphs, equations, arrows).
- "narration" is what the narrator says during that scene: 1 to 3 clear sentences.
- Reuse the notation, terminology and examples from the professor's course material.
- Follow the requested style and tone.
- Respond with only JSON in this exact shape:
{{"title": "<short title>", "scenes": [{{"title": "...", "visual": "...", "narration": "..."}}]}}"""


class StoryboardError(RuntimeError):
    pass


class _Storyboard(BaseModel):
    title: str = Field(min_length=1)
    scenes: list[SceneDraft] = Field(min_length=1, max_length=8)


def language_name(language: Language) -> str:
    return LANGUAGE_NAMES[language]


def generate_storyboard(llm: LLM, *, material: str, concept: str, style: str, tone: str,
                        language: Language) -> tuple[str, list[SceneDraft]]:
    system = SYSTEM_PROMPT.format(language=language_name(language))
    user = (
        f"Concept to explain: {concept}\n"
        f"Style: {style or 'clear and visual'}\n"
        f"Tone: {tone or 'friendly and precise'}\n\n"
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
