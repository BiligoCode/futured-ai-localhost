import asyncio
from datetime import datetime, timezone

import pytest

from app.assess.models import Analysis, AssessmentNotFound, Cluster, PairResult, Paper, PaperNotFound, Question, QuestionResult
from app.assess.store import AssessmentStore, new_paper_id

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def make(tmp_path):
    store = AssessmentStore(tmp_path)
    a = store.create(title="Ενδιάμεση", course="Αλγόριθμοι", language="el", scale=10, instructions="",
                     exam_text="Θέμα 1")
    return store, a


def paper(pid=None, **kw):
    return Paper(id=pid or new_paper_id(), created_at=NOW, filename="a.pdf", **kw)


def test_create_get_list_and_exam_text(tmp_path):
    store, a = make(tmp_path)
    assert store.get(a.id).title == "Ενδιάμεση" and store.exam_text(a.id) == "Θέμα 1"
    assert [x.id for x in store.list()] == [a.id]
    assert (store.assessment_dir(a.id) / "analysis.json").is_file()


@pytest.mark.parametrize("bad", ["", "../etc", "ZZZZZZZZZZ", "0123456789a"])
def test_bad_ids_are_not_found(tmp_path, bad):
    store, _ = make(tmp_path)
    with pytest.raises(AssessmentNotFound):
        store.get(bad)


async def test_papers_and_rows_stay_in_step(tmp_path):
    store, a = make(tmp_path)
    p = paper(student_name="Νίκος")
    await store.add_papers(a.id, [(p, b"%PDF-1.4 fake")])
    assert store.source_path(a.id, p).read_bytes() == b"%PDF-1.4 fake"
    assert store.get(a.id).papers[0].student_name == "Νίκος"

    def rename(x):
        x.student_name = "Νίκος Π."
        x.status = "graded"
    await store.mutate_paper(a.id, p.id, rename)
    row = store.get(a.id).papers[0]
    assert row.student_name == "Νίκος Π." and row.status == "graded"
    with pytest.raises(PaperNotFound):
        store.paper(a.id, "../../x")


async def test_concurrent_paper_updates_do_not_lose_rows(tmp_path):
    store, a = make(tmp_path)
    papers = [paper() for _ in range(12)]
    await store.add_papers(a.id, [(p, b"x") for p in papers])

    async def touch(p):
        await store.mutate_paper(a.id, p.id, lambda x: setattr(x, "status", "read"))
    await asyncio.gather(*(touch(p) for p in papers))
    rows = store.get(a.id).papers
    assert len(rows) == 12 and all(r.status == "read" for r in rows)


async def test_analysis_is_stored_apart_and_cleaned_on_remove(tmp_path):
    store, a = make(tmp_path)
    p1, p2, p3 = paper(), paper(), paper()
    await store.add_papers(a.id, [(p1, b"1"), (p2, b"2"), (p3, b"3")])

    def analysed(x):
        x.analysis = Analysis(status="done", computed_at=NOW, covered=[p1.id, p2.id, p3.id],
                              pairs=[PairResult(a=p1.id, b=p2.id, score=80), PairResult(a=p2.id, b=p3.id, score=20)],
                              clusters=[Cluster(question_id="q", kind="mistake", label="x", members=[p1.id, p2.id])])
    await store.mutate(a.id, analysed)
    assert "pairs" not in (store.assessment_dir(a.id) / "assessment.json").read_text()
    await store.refresh_rows(a.id)
    assert store.get(a.id).row(p1.id).copy_score == 80
    await store.remove_paper(a.id, p2.id)
    got = store.get(a.id)
    assert [r.id for r in got.papers] == [p1.id, p3.id]
    assert got.analysis.pairs == [] and got.analysis.clusters == []
    assert not store.paper_dir(a.id, p2.id).exists()


async def test_new_papers_make_the_analysis_stale(tmp_path):
    store, a = make(tmp_path)
    await store.mutate(a.id, lambda x: setattr(x.analysis, "computed_at", NOW))
    await store.add_papers(a.id, [(paper(), b"x")])
    assert store.get(a.id).analysis.stale


async def test_reset_busy_requeues_and_keeps_finished_work(tmp_path):
    store, a = make(tmp_path)
    reading, grading, graded = paper(status="reading"), paper(status="grading"), paper(status="graded")
    grading.results = [QuestionResult(question_id="q1", points=1)]
    await store.add_papers(a.id, [(reading, b"1"), (grading, b"2"), (graded, b"3")])

    def busy(x):
        x.rubric.status = "drafting"
        x.analysis.status = "running"
    await store.mutate(a.id, busy)
    store.reset_busy(a.id)
    got = store.get(a.id)
    assert [store.paper(a.id, p.id).status for p in (reading, grading, graded)] == ["queued", "read", "graded"]
    assert store.paper(a.id, grading.id).results[0].points == 1
    assert [r.status for r in got.papers] == ["queued", "read", "graded"]
    assert got.rubric.status == "none" and got.analysis.status == "idle" and got.analysis.stale


async def test_delete_removes_everything(tmp_path):
    store, a = make(tmp_path)
    await store.add_papers(a.id, [(paper(), b"x")])
    await store.delete(a.id)
    assert not store.assessment_dir(a.id).exists()
    with pytest.raises(AssessmentNotFound):
        store.get(a.id)


def test_rubric_question_lookup(tmp_path):
    store, a = make(tmp_path)
    a.rubric.questions = [Question(id="q1", label="1", type="open", points=5)]
    assert a.rubric.question("q1").label == "1" and a.rubric.question("zz") is None and a.rubric.max_points == 5
