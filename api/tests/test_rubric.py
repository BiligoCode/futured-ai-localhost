import json

import pytest

from app.assess.models import Criterion, CriterionIn, Question, QuestionIn
from app.assess.rubric import (RubricError, changed_questions, check_gradable, draft_from_images, draft_from_papers,
                               draft_from_text, from_input, parse_draft, scale_criteria)
from tests.fakes import FnLLM, FnVision

DRAFT = {"questions": [
    {"label": "1", "type": "true/false", "prompt": "Η δυαδική αναζήτηση απαιτεί ταξινομημένο πίνακα.", "points": 1,
     "answer": "Σωστό", "key_from": "exam"},
    {"label": "2", "type": "MCQ", "prompt": "Πολυπλοκότητα mergesort;", "points": "1 μονάδα",
     "options": ["α) O(n)", "β) O(n log n)"], "answer": "β", "key_from": "lara"},
    {"label": "3", "type": "number", "prompt": "Συγκρίσεις για n=50;", "points": None, "answer": "50", "tolerance": None},
    {"label": "4", "type": "essay", "prompt": "Εξηγήστε την quicksort.", "points": 6,
     "criteria": [{"text": "διαμέριση", "points": 3}, {"text": "αναδρομή", "points": 3}, {"text": "χειρότερη", "points": 6}]},
    {"label": "4", "type": "weird", "prompt": "Διπλή ετικέτα", "points": 2},
], "note": "Ελέγξτε το κλειδί της 2."}


def test_parse_draft_normalises_types_points_keys_and_labels():
    questions, note = parse_draft(json.dumps(DRAFT, ensure_ascii=False))
    assert [q.type for q in questions] == ["true_false", "multiple_choice", "numeric", "open", "open"]
    assert [q.points for q in questions] == [1, 1, 2, 6, 2]
    assert questions[0].answer == "true" and questions[0].key_from == "exam" and questions[1].key_from == "lara"
    assert [c.points for c in questions[3].criteria] == [1.5, 1.5, 3.0]
    assert [q.label for q in questions][-2:] == ["4", "4 (2)"]
    assert note == "Ελέγξτε το κλειδί της 2." and len({q.id for q in questions}) == 5


def test_scale_criteria_sums_exactly():
    cs = [Criterion(id="c1", text="a", points=1), Criterion(id="c2", text="b", points=1), Criterion(id="c3", text="c", points=1)]
    assert sum(c.points for c in scale_criteria(cs, 5)) == 5


def test_drafting_retries_and_reports():
    replies = iter(["garbage", json.dumps(DRAFT, ensure_ascii=False)])
    llm = FnLLM(lambda s, m: next(replies))
    questions, _ = draft_from_text(llm, "Θέμα 1 …", "el", title="Ενδιάμεση")
    assert len(questions) == 5 and len(llm.calls) == 2
    assert "Greek" in llm.calls[0][1][0]["content"] and "Θέμα 1" in llm.calls[0][1][0]["content"]
    with pytest.raises(RubricError):
        draft_from_text(FnLLM(lambda s, m: "{}"), "x", "en")


def test_drafting_from_images_and_papers():
    vision = FnVision(lambda s, p, i: json.dumps(DRAFT))
    questions, _ = draft_from_images(vision, [b"1", b"2"], "en")
    assert len(questions) == 5 and vision.calls[0][2] == 2
    llm = FnLLM(lambda s, m: json.dumps(DRAFT))
    draft_from_papers(llm, ["paper one", "paper two"], "en")
    assert "never take a key from them" in llm.calls[0][1][0]["content"]


def q(**kw):
    base = dict(label="1", type="open", points=5)
    return QuestionIn(**(base | kw))


def test_from_input_keeps_known_ids_and_renumbers_criteria():
    existing = [Question(id="aaaaaa", label="1", type="open", points=5)]
    out = from_input([q(id="aaaaaa", criteria=[CriterionIn(id="x", text="a", points=2), CriterionIn(text="b", points=3)]),
                      q(id="aaaaaa", label="2"), q(id="zzzzzz", label="3", type="true_false", answer="Λ")], existing)
    assert out[0].id == "aaaaaa" and [c.id for c in out[0].criteria] == ["c1", "c2"]
    assert out[1].id != "aaaaaa" and out[2].id != "zzzzzz" and out[2].answer == "false"


@pytest.mark.parametrize("questions,error", [
    ([], "Add at least one question before grading"),
    ([Question(id="a", label="1", type="true_false", points=1, answer="maybe")], "true or false for question: 1"),
    ([Question(id="a", label="2", type="multiple_choice", points=1, answer="", options=["α) x"])], "correct option for question: 2"),
    ([Question(id="a", label="3", type="numeric", points=1, answer="—")], "correct number for question: 3"),
    ([Question(id="a", label="4", type="short", points=1, answer=" ")], "expected answer for question: 4"),
    ([Question(id="a", label="5", type="open", points=5, criteria=[Criterion(id="c1", text="x", points=2)])], "add up to the points of question: 5"),
    ([Question(id="a", label="1", type="open", points=1), Question(id="b", label="1", type="open", points=1)], "same label: 1"),
])
def test_check_gradable(questions, error):
    assert error in check_gradable(questions)


def test_gradable_rubric_passes():
    assert check_gradable([Question(id="a", label="1", type="multiple_choice", points=1, answer="b", options=["a) x", "b) y"]),
                           Question(id="b", label="2", type="numeric", points=2, answer="0,5")]) is None


def test_changed_questions():
    a = Question(id="a", label="1", type="numeric", points=2, answer="5")
    b = Question(id="b", label="2", type="open", points=5, criteria=[Criterion(id="c1", text="x", points=5)])
    assert changed_questions([a, b], [a.model_copy(update={"label": "1α", "prompt": "new"}), b]) == set()
    assert changed_questions([a, b], [a.model_copy(update={"answer": "6"}), b]) == {"a"}
    b2 = b.model_copy(update={"criteria": [Criterion(id="c1", text="y", points=5)]})
    assert changed_questions([a, b], [a, b2, Question(id="c", label="3", type="open", points=1)]) == {"b", "c"}
