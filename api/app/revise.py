"""Turn a professor's change request about the whole video into edits of specific scenes."""
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.llm import LLM
from app.models import Cut, Project
from app.parsing import extract_json
from app.storyboard import check_language, language_name

_TIMESTAMP = re.compile(r"(?<![\d:])(\d{1,2}):([0-5]\d)(?![\d:])")

SYSTEM_PROMPT = """You help a professor change an animated explanation video. The video is made of numbered \
parts that play one after the other; the professor sees only one video and refers to moments in it by what \
happens on screen, by what is said, or by a timestamp.

Decide which parts the request is about and what must change in each:
- Pick only the parts the request concerns. A timestamp points to the part playing at that time, unless the \
description clearly matches another part. A request about the whole video (e.g. "use blue everywhere") \
concerns every part it affects.
- "animation": true when what is shown on screen must change. Then "instruction" is a precise, self-contained \
instruction for the animator about this part only, in English (quote any on-screen text exactly).
- "narration": the complete new narration for the part, in {language} (whatever language the request is \
written in), when what is said must change (explain \
differently, more or less detail, correct a statement); otherwise null. When the explanation changes in a way \
the visuals should follow, also set "animation".
- "summary": one short sentence in {language} telling the professor what you will change.

Respond with only JSON in this exact shape:
{{"edits": [{{"part": <number>, "animation": true, "instruction": "...", "narration": null, "summary": "..."}}]}}"""


class RevisionError(RuntimeError):
    pass


@dataclass
class Edit:
    scene_id: str
    animation: bool
    instruction: str
    narration: str | None
    summary: str


class _Edit(BaseModel):
    part: int
    animation: bool = False
    instruction: str = ""
    narration: str | None = None
    summary: str = Field(min_length=1)


class _Plan(BaseModel):
    edits: list[_Edit] = Field(min_length=1)


def parse_timestamps(text: str) -> list[float]:
    return [int(m.group(1)) * 60 + int(m.group(2)) for m in _TIMESTAMP.finditer(text)]


def clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def _part_number(project: Project, cut: Cut | None, seconds: float) -> int | None:
    scene_id = cut.scene_at(seconds) if cut else None
    return next((i + 1 for i, s in enumerate(project.scenes) if s.id == scene_id), None)


def _brief(project: Project, cut: Cut | None, instruction: str, at_seconds: float | None) -> str:
    times = {seg.scene_id: seg for seg in cut.segments} if cut else {}
    lines = []
    for i, scene in enumerate(project.scenes, 1):
        seg = times.get(scene.id)
        span = f" ({clock(seg.start)}–{clock(seg.end)})" if seg else ""
        lines.append(f"Part {i}{span}: {scene.title}\n  On screen: {scene.visual}\n  Narration: {scene.narration}")
    hints = []
    for t in parse_timestamps(instruction):
        part = _part_number(project, cut, t)
        if part:
            hints.append(f"The timestamp {clock(t)} in the request falls in part {part}.")
    if at_seconds is not None:
        part = _part_number(project, cut, at_seconds)
        if part:
            hints.append(f"The professor's player was at {clock(at_seconds)} (part {part}) when they asked; "
                         "this is only a hint.")
    return ("Parts of the video:\n" + "\n".join(lines) + "\n\n" + "\n".join(hints) +
            f"\n\nThe professor's request:\n<<<\n{instruction}\n>>>")


def _validate(plan: _Plan, project: Project) -> list[Edit]:
    edits: dict[str, Edit] = {}
    for e in plan.edits:
        if not 1 <= e.part <= len(project.scenes):
            raise ValueError(f"part {e.part} does not exist (there are {len(project.scenes)} parts)")
        narration = e.narration.strip() if e.narration and e.narration.strip() else None
        animation = e.animation and bool(e.instruction.strip())
        if not animation and narration is None:
            continue
        scene = project.scenes[e.part - 1]
        if narration:
            check_language([narration], project.language)
        edits[scene.id] = Edit(scene_id=scene.id, animation=animation, instruction=e.instruction.strip(),
                               narration=narration if narration != scene.narration else None, summary=e.summary)
    if not edits:
        raise ValueError("no part was given an animation instruction or a new narration")
    return list(edits.values())


def plan_revision(llm: LLM, project: Project, instruction: str, *, cut: Cut | None,
                  at_seconds: float | None = None) -> list[Edit]:
    system = SYSTEM_PROMPT.format(language=language_name(project.language))
    messages = [{"role": "user", "content": _brief(project, cut, instruction, at_seconds)}]
    error = ""
    for _ in range(2):
        reply = llm(system, messages)
        try:
            return _validate(_Plan.model_validate(extract_json(reply)), project)
        except (ValueError, ValidationError) as exc:
            error = str(exc)
            messages = messages + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"Your previous reply was not valid: {error}. Reply with only the JSON."},
            ]
    # The model could not route it; a timestamp the professor gave is still a reliable pointer.
    times = parse_timestamps(instruction) or ([at_seconds] if at_seconds is not None else [])
    scene_id = cut.scene_at(times[0]) if cut and times else None
    if scene_id:
        return [Edit(scene_id=scene_id, animation=True, instruction=instruction, narration=None,
                     summary=instruction)]
    raise RevisionError(f"Could not work out which part of the video to change: {error}")
