"""Class statistics for the overview (design §4: AssessmentView.stats), computed from the paper rows alone."""
import statistics
from collections import Counter

from app.assess.models import BUSY_STATUSES, Assessment, AssessmentSummary, HistogramBin, QuestionStats, Stats

HIGH = 60


def is_busy(a: Assessment) -> bool:
    if a.paused:
        return False
    waiting = a.rubric.status == "confirmed" and any(
        r.status == "read" or (r.status == "graded" and r.rubric_version != a.rubric.version) for r in a.papers)
    return (any(r.status in BUSY_STATUSES for r in a.papers) or a.rubric.status == "drafting"
            or a.analysis.status == "running" or waiting)


def flagged(row) -> bool:
    return (row.ai_score or 0) >= HIGH or (row.copy_score or 0) >= HIGH or row.alerts > 0


def compute_stats(a: Assessment) -> Stats:
    rows = a.papers
    graded = [r for r in rows if r.status == "graded" and r.grade is not None]
    grades = [r.grade for r in graded]
    s = Stats(total=len(rows), counts=dict(Counter(r.status for r in rows)), graded=len(graded), busy=is_busy(a),
              needs_review=sum(1 for r in rows if r.needs_review), reviewed=sum(1 for r in rows if r.reviewed),
              flagged=sum(1 for r in rows if flagged(r)))
    if grades:
        s.mean = round(statistics.mean(grades), 2)
        s.median = round(statistics.median(grades), 2)
        s.sd = round(statistics.pstdev(grades), 2)
        s.min, s.max = min(grades), max(grades)
        s.pass_rate = round(sum(1 for g in grades if g >= a.scale / 2) / len(grades), 3)
    width = a.scale / 10
    bins = [HistogramBin(start=round(i * width, 2), end=round((i + 1) * width, 2), count=0) for i in range(10)]
    for g in grades:
        bins[min(9, int(g // width))].count += 1
    s.histogram = bins
    for q in a.rubric.questions:
        marks = [r.marks[q.id] for r in graded if q.id in r.marks]
        qs = QuestionStats(question_id=q.id, graded=len(marks))
        if marks:
            qs.mean_pct = round(statistics.mean(m / q.points for m in marks), 3)
            if q.type != "open":
                qs.correct_rate = round(sum(1 for m in marks if m >= q.points - 1e-9) / len(marks), 3)
        if q.type in ("true_false", "multiple_choice"):
            picks = [r.picks.get(q.id, "") for r in graded if q.id in r.marks]
            qs.distribution = dict(Counter(p or "—" for p in picks).most_common())
            qs.answered = sum(1 for p in picks if p)
        else:
            qs.answered = sum(1 for m in marks if m > 0)
        s.questions.append(qs)
    return s


def summarize(a: Assessment) -> AssessmentSummary:
    s = compute_stats(a)
    return AssessmentSummary(id=a.id, created_at=a.created_at, updated_at=a.updated_at, title=a.title, course=a.course,
                             language=a.language, scale=a.scale, rubric_status=a.rubric.status, papers=s.total,
                             graded=s.graded, busy=s.busy, paused=a.paused, mean=s.mean, needs_review=s.needs_review,
                             flagged=s.flagged, histogram=[b.count for b in s.histogram])
