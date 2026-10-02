"""Marks in code (design §6.4): definitive answers are compared with the key here, never by the model.

`rescore` derives everything a result shows (status, correctness, points, feedback, flags) from what was read and
what the grader said, so a professor's corrected reading is re-scored instantly and identically."""
import math
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.assess.answers import (is_blank, key_alternatives, numbers_match, option_letter, parse_choices,
                                parse_numbers, parse_true_false, short_matches)
from app.assess.models import Assessment, Paper, PaperRow, Question, QuestionResult

POINT_STEP = 0.25
REVIEW_FLAGS = frozenset({"readings_differ", "unclear_reading", "key_proposed", "notation_ambiguous",
                          "addresses_grader", "missing_answer"})
HIGH_SCORE = 60


class RawAnswer(BaseModel):
    """One question as the grading model reported it (design §6.3)."""
    q: str
    page: int | None = None
    answer: str = ""
    final: str | None = None
    unreadable: bool = False
    matches_key: bool | None = None
    criteria: dict[str, float] = {}
    points: float | None = None
    feedback: str = ""
    errors: list[str] = Field(default_factory=list)
    specifics: list[str] = Field(default_factory=list)
    confidence: str = "high"
    addresses_grader: bool = False


def round_points(value: float) -> float:
    return round(value / POINT_STEP) * POINT_STEP


def clamp_points(value: float | None, maximum: float) -> float:
    if value is None or not math.isfinite(value):
        return 0.0
    return min(maximum, max(0.0, round_points(value)))


_TEXT = {
    "en": {
        "correct": "Correct.",
        "unanswered": "Not answered.",
        "unreadable": "The answer cannot be read clearly — check the scan.",
        "tf_wrong": "Answered “{got}”; the correct answer is “{key}”.",
        "mc_wrong": "Chose {got}; the correct answer is {key}.",
        "num_ok": "Correct result ({key}).",
        "num_wrong": "Answered {got}; the correct answer is {key}.",
        "true": "True", "false": "False",
    },
    "el": {
        "correct": "Σωστό.",
        "unanswered": "Δεν απαντήθηκε.",
        "unreadable": "Η απάντηση δεν διαβάζεται καθαρά — ελέγξτε τη σάρωση.",
        "tf_wrong": "Απάντησε «{got}»· η σωστή απάντηση είναι «{key}».",
        "mc_wrong": "Επέλεξε {got}· η σωστή απάντηση είναι {key}.",
        "num_ok": "Σωστό αποτέλεσμα ({key}).",
        "num_wrong": "Απάντησε {got}· η σωστή απάντηση είναι {key}.",
        "true": "Σωστό", "false": "Λάθος",
    },
}


def _t(language: str, message: str, **kw) -> str:
    return _TEXT["el" if language == "el" else "en"][message].format(**kw)


def _letters(indexes: frozenset[int], like: str) -> str:
    return ", ".join(option_letter(i, like) for i in sorted(indexes))


def _short(text: str | None, limit: int = 60) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


_TRANSCRIPT_MARKS = re.compile(r"\s*⟶ final:[^\n]*|\s*\(reader's notes:[^)]*\)")


def clean_excerpt(text: str) -> str:
    """The grader sometimes copies the transcript's own markers into an answer: drop them."""
    return _TRANSCRIPT_MARKS.sub("", text or "").strip()


def score_result(question: Question, raw: RawAnswer, language: str) -> QuestionResult:
    confidence = raw.confidence if raw.confidence in ("high", "medium", "low") else "medium"
    criteria = {k: v for k, v in raw.criteria.items() if any(c.id == k for c in question.criteria)}
    result = QuestionResult(
        question_id=question.id, page=raw.page, answer=clean_excerpt(raw.answer)[:1500],
        final=None if raw.final is None else str(raw.final)[:300], max_points=question.points,
        criteria={k: (1.0 if v >= 0.75 else 0.5 if v >= 0.25 else 0.0) for k, v in criteria.items()},
        errors=[e[:200] for e in raw.errors][:8], specifics=[s[:200] for s in raw.specifics][:8],
        confidence=confidence, model_confidence=confidence, model_points=raw.points, matches_key=raw.matches_key,
        model_feedback=(raw.feedback or "")[:2000],
        flags=(["unclear_reading"] if raw.unreadable else []) + (["addresses_grader"] if raw.addresses_grader else []),
    )
    return rescore(question, result, language)


def rescore(question: Question, result: QuestionResult, language: str) -> QuestionResult:
    """Status, correctness, points and feedback from the reading (or the professor's corrected reading)."""
    r = result.model_copy(deep=True)
    r.max_points = question.points
    r.confidence = r.model_confidence
    keep = {"unclear_reading", "addresses_grader", "readings_differ", "missing_answer"}
    flags = [f for f in r.flags if f in keep]
    if r.override_final is not None:
        flags = [f for f in flags if f not in ("readings_differ", "unclear_reading")]
    final = r.override_final if r.override_final is not None else r.final
    unreadable = "unclear_reading" in flags or (final is not None and "[?]" in final)
    if question.type in ("true_false", "multiple_choice", "numeric", "short") and question.key_from == "lara":
        flags.append("key_proposed")
    kind = question.type
    r.correct = None

    def done(status: str, points: float, feedback: str) -> QuestionResult:
        r.status = status
        r.points = clamp_points(points, question.points)
        r.feedback = feedback
        r.flags = list(dict.fromkeys(flags))
        if r.flags and any(f in REVIEW_FLAGS for f in r.flags) and r.confidence == "high":
            r.confidence = "medium"
        if unreadable or "readings_differ" in r.flags or "notation_ambiguous" in r.flags:
            r.confidence = "low"
        return r

    if kind == "open":
        if is_blank(r.answer) and is_blank(final):
            return done("unanswered", 0, _t(language, "unanswered"))
        if question.criteria:
            points = sum(r.criteria.get(c.id, 0.0) * c.points for c in question.criteria)
        else:
            points = r.model_points or 0.0
        points = clamp_points(points, question.points)
        status = "correct" if points >= question.points else "incorrect" if points <= 0 else "partial"
        return done(status, points, r.model_feedback)

    if is_blank(final):
        if unreadable:
            return done("unreadable", 0, _t(language, "unreadable"))
        return done("unanswered", 0, _t(language, "unanswered"))

    if kind == "true_false":
        got, key = parse_true_false(final), parse_true_false(question.answer)
        if got is None or key is None:
            flags.append("unclear_reading")
            unreadable = True
            return done("unreadable", 0, _t(language, "unreadable"))
        r.correct = got == key
        if r.correct:
            return done("correct", question.points, _t(language, "correct"))
        word = lambda v: _t(language, "true" if v else "false")  # noqa: E731
        return done("incorrect", 0, _t(language, "tf_wrong", got=word(got), key=word(key)))

    if kind == "multiple_choice":
        got = parse_choices(final, question.options)
        key = parse_choices(question.answer, question.options, n_options=max(len(question.options), 8))
        if got is None or key is None:
            flags.append("unclear_reading")
            unreadable = True
            return done("unreadable", 0, _t(language, "unreadable"))
        r.correct = got == key
        if question.options and max(got) >= len(question.options):
            flags.append("unclear_reading")  # not one of the options: most likely a misreading
            unreadable = True
        if r.correct:
            return done("correct", question.points, _t(language, "correct"))
        return done("incorrect", 0, _t(language, "mc_wrong", got=_letters(got, question.answer or final),
                                       key=_letters(key, question.answer)))

    if kind == "numeric":
        keys = parse_numbers(question.answer)
        got = parse_numbers(final)
        if not keys:
            flags.append("key_proposed")
            return done("unreadable", 0, _t(language, "unreadable"))
        if not got:
            flags.append("unclear_reading")
            unreadable = True
            return done("unreadable", 0, _t(language, "unreadable"))
        key = keys[0]
        r.correct = numbers_match(got, key, question.tolerance)
        if r.correct and len(got) > 1 and not numbers_match(got[:1], key, question.tolerance):
            flags.append("notation_ambiguous")
        if r.correct:
            return done("correct", question.points, _t(language, "num_ok", key=_short(question.answer)))
        wrong = _t(language, "num_wrong", got=_short(final), key=_short(question.answer))
        if question.partial and (r.model_points or 0) > 0:
            points = min(clamp_points(r.model_points, question.points), question.points - POINT_STEP)
            return done("partial" if points > 0 else "incorrect", points, r.model_feedback or wrong)
        return done("incorrect", 0, wrong)

    # short
    exact = short_matches(final, question.answer)
    r.correct = exact or bool(r.matches_key)
    if r.correct:
        return done("correct", question.points, _t(language, "correct") if exact else (r.model_feedback or _t(language, "correct")))
    if question.partial and (r.model_points or 0) > 0:
        points = min(clamp_points(r.model_points, question.points), question.points - POINT_STEP)
        return done("partial" if points > 0 else "incorrect", points, r.model_feedback)
    alternatives = key_alternatives(question.answer)
    return done("incorrect", 0, r.model_feedback or _t(language, "num_wrong", got=_short(final),
                                                        key=_short(alternatives[0] if alternatives else "")))


def unanswered_result(question: Question, language: str) -> QuestionResult:
    """A question the grader did not report at all (after its retry): nothing found, to be checked."""
    r = QuestionResult(question_id=question.id, max_points=question.points, confidence="low", model_confidence="low",
                       flags=["missing_answer"])
    return rescore(question, r, language)


# --- Totals, review, rows ---------------------------------------------------------------------------------------

def effective_points(result: QuestionResult) -> float:
    return result.override_points if result.override_points is not None else result.points


def paper_points(paper: Paper, assessment: Assessment) -> tuple[float, float]:
    """(points, maximum) over the current rubric; questions without a result count 0."""
    total = 0.0
    for q in assessment.rubric.questions:
        if (r := paper.result(q.id)) is not None:
            total += min(effective_points(r), q.points)
    return total, assessment.rubric.max_points


def grade_of(points: float, maximum: float, scale: int) -> float | None:
    if maximum <= 0:
        return None
    return round(points / maximum * scale + 1e-9, 1)


def review_flags(paper: Paper) -> int:
    """Questions that still need the professor's eyes (a corrected reading or mark settles one)."""
    count = 0
    for r in paper.results:
        handled = r.override_points is not None or r.override_final is not None
        if not handled and (r.confidence == "low" or any(f in REVIEW_FLAGS for f in r.flags)):
            count += 1
    return count


def alerts(paper: Paper) -> int:
    return sum(1 for f in (paper.forensics.findings if paper.forensics else []) if f.severity == "alert")


def best_match(assessment: Assessment, paper_id: str) -> tuple[int | None, str | None]:
    best: tuple[int | None, str | None] = (None, None)
    if paper_id not in assessment.analysis.covered:
        return best
    known = {r.id for r in assessment.papers}
    for pair in assessment.analysis.pairs:
        if paper_id in (pair.a, pair.b):
            other = pair.b if pair.a == paper_id else pair.a
            if other in known and (best[0] is None or pair.score > best[0]):
                best = (pair.score, other)
    return best if best[0] is not None else (0, None)


def pick_of(question: Question, result: QuestionResult) -> str:
    """What a true/false or multiple-choice answer was, in one comparable form ("" when blank or unreadable)."""
    final = result.override_final if result.override_final is not None else result.final
    if question.type == "true_false":
        value = parse_true_false(final)
        return "" if value is None else ("true" if value else "false")
    if question.type == "multiple_choice":
        chosen = parse_choices(final, question.options)
        return ",".join(option_letter(i, question.answer) for i in sorted(chosen)) if chosen else ""
    return ""


def build_row(paper: Paper, assessment: Assessment) -> PaperRow:
    graded = paper.status == "graded" or (paper.results and paper.status in ("grading", "read"))
    points, maximum = paper_points(paper, assessment)
    marks: dict[str, float] = {}
    picks: dict[str, str] = {}
    if graded:
        for q in assessment.rubric.questions:
            if (r := paper.result(q.id)) is not None:
                marks[q.id] = min(effective_points(r), q.points)
                if q.type in ("true_false", "multiple_choice"):
                    picks[q.id] = pick_of(q, r)
    copy_score, copy_match = best_match(assessment, paper.id)
    flags = review_flags(paper)
    ai_score = paper.ai.score if paper.ai else None
    n_alerts = alerts(paper)
    needs = not paper.reviewed and (
        paper.status == "failed" or flags > 0 or n_alerts > 0
        or (ai_score or 0) >= HIGH_SCORE or (copy_score or 0) >= HIGH_SCORE)
    return PaperRow(
        id=paper.id, filename=paper.filename, student_name=paper.student_name, student_id=paper.student_id,
        status=paper.status, error=paper.error, page_count=len(paper.pages),
        points=round(points, 2) if graded else None, max_points=maximum,
        grade=grade_of(points, maximum, assessment.scale) if graded else None,
        ai_score=ai_score, ai_level=paper.ai.level if paper.ai else None,
        ai_signals=[x.code for x in paper.ai.signals[:3]] if paper.ai else [],
        findings=[f.code for f in (paper.forensics.findings if paper.forensics else []) if f.severity != "info"],
        copy_score=copy_score, copy_match=copy_match, alerts=n_alerts, review_flags=flags,
        needs_review=bool(needs), reviewed=paper.reviewed, rubric_version=paper.rubric_version, marks=marks, picks=picks,
        created_at=paper.created_at, updated_at=paper.updated_at or datetime.now(timezone.utc),
    )
