import pytest

from app.storyboard import StoryboardError, generate_storyboard
from tests.fakes import STORYBOARD_JSON, ScriptedLLM

ARGS = dict(material="Course notes on optimisation", concept="gradient descent", style="visual",
            tone="friendly", language="el")


def test_parses_valid_storyboard():
    title, scenes = generate_storyboard(ScriptedLLM([STORYBOARD_JSON]), **ARGS)
    assert title == "Κάθοδος κλίσης" and len(scenes) == 4 and all(s.narration for s in scenes)


def test_prompt_contains_inputs():
    llm = ScriptedLLM([STORYBOARD_JSON])
    generate_storyboard(llm, **ARGS)
    system, messages = llm.calls[0]
    text = system + messages[0]["content"]
    assert "gradient descent" in text and "Course notes on optimisation" in text and "Greek" in text


def test_retries_once_on_invalid_json():
    llm = ScriptedLLM(["not json", STORYBOARD_JSON])
    assert len(generate_storyboard(llm, **ARGS)[1]) == 4
    assert len(llm.calls) == 2 and "not valid" in llm.calls[1][1][-1]["content"].lower()


def test_retries_on_empty_scene_field():
    bad = '{"title": "t", "scenes": [{"title": "a", "visual": "", "narration": "n"}]}'
    llm = ScriptedLLM([bad, STORYBOARD_JSON])
    generate_storyboard(llm, **ARGS)
    assert len(llm.calls) == 2


def test_raises_after_second_failure():
    with pytest.raises(StoryboardError):
        generate_storyboard(ScriptedLLM(["x", "y"]), **ARGS)
