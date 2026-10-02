from datetime import datetime, timezone

import pytest

from app.assess.models import (AiAnalysis, Analysis, Assessment, Criterion, Finding, Forensics, PairResult, Paper,
                               Question, QuestionResult, Rubric)
from app.assess.scoring import (RawAnswer, build_row, clamp_points, grade_of, paper_points, rescore, review_flags,
                                score_result, unanswered_result)

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
TF = Question(id="q1", label="1", type="true_false", points=1, answer="true")
MC = Question(id="q2", label="2", type="multiple_choice", points=1, answer="β",
              options=["α) O(n)", "β) O(n log n)", "γ) O(n^2)", "δ) O(log n)"])
NUM = Question(id="q3", label="3", type="numeric", points=2, answer="208")
NUM_PARTIAL = NUM.model_copy(update={"partial": True})
SHORT = Question(id="q4", label="4", type="short", points=2, answer="O(n log n) | n log n")
OPEN = Question(id="q5", label="5", type="open", points=6, criteria=[
    Criterion(id="c1", text="partition", points=2), Criterion(id="c2", text="recursion", points=1),
    Criterion(id="c3", text="worst case cause", points=2), Criterion(id="c4", text="sum", points=1)])


def raw(q, **kw):
    return RawAnswer(q=q, **kw)


def test_true_false_in_greek_is_scored_in_code():
    r = score_result(TF, raw("q1", final="Σ"), "el")
    assert (r.status, r.correct, r.points, r.feedback) == ("correct", True, 1, "Σωστό.")
    r = score_result(TF, raw("q1", final="Λ"), "el")
    assert (r.status, r.correct, r.points) == ("incorrect", False, 0)
    assert r.feedback == "Απάντησε «Λάθος»· η σωστή απάντηση είναι «Σωστό»."


def test_multiple_choice_wrong_letter_even_if_model_would_say_right():
    r = score_result(MC, raw("q2", final="γ", feedback="Σωστό!"), "el")
    assert (r.status, r.correct, r.points) == ("incorrect", False, 0)
    assert r.feedback == "Επέλεξε γ· η σωστή απάντηση είναι β."
    assert score_result(MC, raw("q2", final="b"), "en").correct is True


def test_numeric_with_decimal_comma_and_partial_credit():
    assert score_result(NUM, raw("q3", final="208 βιβλία"), "el").correct is True
    r = score_result(NUM, raw("q3", final="200", points=1.5), "en")
    assert (r.status, r.points) == ("incorrect", 0)  # no partial credit unless the rubric allows it
    r = score_result(NUM_PARTIAL, raw("q3", final="200", points=1.5, feedback="Right method, slip at the end."), "en")
    assert (r.status, r.points, r.feedback) == ("partial", 1.5, "Right method, slip at the end.")
    r = score_result(NUM_PARTIAL, raw("q3", final="200", points=5), "en")
    assert r.points == 1.75  # partial credit never reaches full marks


def test_ambiguous_notation_is_flagged():
    q = Question(id="q", label="x", type="numeric", points=1, answer="1")
    r = score_result(q, raw("q", final="1.000"), "en")
    assert r.correct is True and "notation_ambiguous" in r.flags and r.confidence == "low"


def test_short_answer_exact_or_model_equivalence():
    assert score_result(SHORT, raw("q4", final="O(nlogn)"), "en").status == "correct"
    r = score_result(SHORT, raw("q4", final="linearithmic", matches_key=True, feedback="Equivalent."), "en")
    assert (r.status, r.feedback) == ("correct", "Equivalent.")
    assert score_result(SHORT, raw("q4", final="O(n)", matches_key=False, feedback="No."), "en").status == "incorrect"


def test_open_question_is_scored_per_criterion():
    r = score_result(OPEN, raw("q5", answer="Διαμέριση γύρω από τον άξονα", criteria={"c1": 1, "c2": 1, "c3": 0.5, "c4": 0, "zz": 1},
                               points=6, feedback="Good."), "el")
    assert r.points == 4.0 and r.status == "partial" and r.criteria == {"c1": 1, "c2": 1, "c3": 0.5, "c4": 0}
    no_criteria = OPEN.model_copy(update={"criteria": []})
    assert score_result(no_criteria, raw("q5", answer="Διαμέριση γύρω από τον άξονα", points=9), "el").points == 6
    assert score_result(OPEN, raw("q5", answer="", final=None), "el").status == "unanswered"


def test_unanswered_and_unreadable():
    assert score_result(TF, raw("q1", final=None), "en").status == "unanswered"
    r = score_result(TF, raw("q1", final="", unreadable=True), "en")
    assert r.status == "unreadable" and r.confidence == "low" and "unclear_reading" in r.flags
    r = score_result(MC, raw("q2", final="β[?]"), "en")
    assert r.confidence == "low"


def test_professor_corrects_the_reading():
    r = score_result(NUM, raw("q3", final="200"), "en")
    r.flags.append("readings_differ")
    r.second_final = "208"
    r = rescore(NUM, r, "en")
    assert r.confidence == "low" and "readings_differ" in r.flags
    r.override_final = "208"
    r = rescore(NUM, r, "en")
    assert r.correct is True and r.points == 2 and "readings_differ" not in r.flags and r.confidence == "high"


def test_key_proposed_by_lara_is_flagged():
    q = TF.model_copy(update={"key_from": "lara"})
    r = score_result(q, raw("q1", final="Σ"), "el")
    assert "key_proposed" in r.flags and r.confidence == "medium"


def test_points_are_clamped_and_rounded():
    assert clamp_points(2.13, 6) == 2.25 and clamp_points(-1, 6) == 0 and clamp_points(99, 6) == 6
    assert clamp_points(None, 6) == 0 and clamp_points(float("nan"), 6) == 0


def test_missing_answer_needs_review():
    r = unanswered_result(OPEN, "el")
    assert r.status == "unanswered" and r.confidence == "low" and "missing_answer" in r.flags


def make_assessment(**kw):
    return Assessment(id="a1", created_at=NOW, updated_at=NOW, title="T", language="el", scale=10,
                      rubric=Rubric(status="confirmed", version=1, questions=[TF, MC, NUM, OPEN]), **kw)


def make_paper(**kw):
    base = dict(id="p1", created_at=NOW, filename="a.pdf", status="graded", rubric_version=1)
    return Paper(**(base | kw))


def test_points_grade_and_overrides():
    a = make_assessment()
    p = make_paper(results=[
        score_result(TF, raw("q1", final="Σ"), "el"),
        score_result(MC, raw("q2", final="γ"), "el"),
        score_result(NUM, raw("q3", final="208"), "el"),
        score_result(OPEN, raw("q5", answer="Διαμέριση γύρω από τον άξονα", criteria={"c1": 1, "c2": 1}), "el"),
    ])
    assert paper_points(p, a) == (6.0, 10.0)
    p.results[1].override_points = 1
    assert paper_points(p, a) == (7.0, 10.0)
    assert grade_of(7, 10, 10) == 7.0 and grade_of(13, 20, 20) == 13.0 and grade_of(2, 3, 10) == 6.7
    assert grade_of(1, 0, 10) is None


def test_row_reflects_paper_and_needs_review():
    a = make_assessment()
    p = make_paper(results=[score_result(TF, raw("q1", final="Σ"), "el")], student_name="Μαρία")
    row = build_row(p, a)
    assert (row.points, row.max_points, row.grade, row.needs_review, row.student_name) == (1.0, 10.0, 1.0, False, "Μαρία")
    assert row.copy_score is None  # not analysed yet
    p.results.append(score_result(MC, raw("q2", final="", unreadable=True), "el"))
    assert review_flags(p) == 1 and build_row(p, a).needs_review
    p.reviewed = True
    assert not build_row(p, a).needs_review


def test_row_scores_from_ai_forensics_and_pairs():
    a = make_assessment(analysis=Analysis(status="done", computed_at=NOW, covered=["p1", "p2"],
                                          pairs=[PairResult(a="p1", b="p2", score=72)]))
    a.papers = []
    p = make_paper(ai=AiAnalysis(score=10, level="low"),
                   forensics=Forensics(findings=[Finding(code="hidden_text", severity="alert")]))
    row = build_row(p, a)
    assert row.alerts == 1 and row.needs_review
    from app.assess.models import PaperRow
    a.papers = [PaperRow(id="p2", filename="b.pdf", created_at=NOW, updated_at=NOW)]
    row = build_row(p, a)
    assert (row.copy_score, row.copy_match) == (72, "p2")


@pytest.mark.parametrize("status,expected", [("queued", None), ("graded", 1.0)])
def test_row_has_no_grade_before_grading(status, expected):
    a = make_assessment()
    results = [score_result(TF, raw("q1", final="Σ"), "el")] if status == "graded" else []
    assert build_row(make_paper(status=status, results=results), a).points == expected


def test_result_model_defaults():
    r = QuestionResult(question_id="x")
    assert r.status == "unanswered" and r.points == 0


def test_transcript_markers_are_not_kept_in_answers():
    r = score_result(NUM, raw("q3", answer="log2(1024) = 10 ⟶ final: 10\n(reader's notes: faint)", final="10"), "en")
    assert r.answer == "log2(1024) = 10"
