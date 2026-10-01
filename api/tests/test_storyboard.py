import json

import pytest

from app.storyboard import StoryboardError, generate_storyboard
from tests.fakes import STORYBOARD_JSON, ScriptedLLM

ARGS = dict(material="Course notes on optimisation", concept="gradient descent", style="visual",
            duration="short", language="el")


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


def test_raises_after_three_failures():
    with pytest.raises(StoryboardError):
        generate_storyboard(ScriptedLLM(["x", "y", "z"]), **ARGS)


ENGLISH_JSON = json.dumps({"title": "Gradient descent", "scenes": [
    {"title": "The problem", "visual": "A cost curve", "narration": "We want the minimum of the cost function."}]})


def test_selected_language_wins_over_the_language_of_the_input():
    # The professor typed English, but selected Greek: an English draft is rejected and redone in Greek.
    llm = ScriptedLLM([ENGLISH_JSON, STORYBOARD_JSON])
    title, _ = generate_storyboard(llm, **{**ARGS, "concept": "gradient descent", "material": "English notes"})
    assert title == "Κάθοδος κλίσης"
    assert "must be written in Greek" in llm.calls[1][1][-1]["content"]
    assert "Write the video in: Greek" in llm.calls[0][1][0]["content"]


def test_english_selected_rejects_greek_draft():
    llm = ScriptedLLM([STORYBOARD_JSON, ENGLISH_JSON])
    title, _ = generate_storyboard(llm, **{**ARGS, "language": "en"})
    assert title == "Gradient descent" and "must be written in English" in llm.calls[1][1][-1]["content"]


def test_greek_with_notation_counts_as_greek():
    from app.storyboard import check_language
    check_language(["Η πολυπλοκότητα είναι O(n log n) και ο πίνακας dp[i] γεμίζει από αριστερά"], "el")


def test_words_from_other_scripts_are_rejected():
    import pytest as _pytest
    from app.storyboard import check_language
    with _pytest.raises(ValueError, match="плюс"):
        check_language(["Το dp[i] γίνεται 1 плюс το ελάχιστο dp[i-c]."], "el")
