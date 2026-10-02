"""Assessments API (design §11)."""
import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.assess.export import MEDIA_TYPES, export_assessment
from app.assess.ingest import UploadError, sniff, split_upload
from app.assess.models import (Assessment, AssessmentSummary, AssessmentUpdate, AssessmentView, ExportRequest, PairResult,
                               Paper, PaperRow, PaperUpdate, RubricUpdate)
from app.assess.pipeline import AssessmentPipeline, exam_files_text, paper_key
from app.assess.rubric import changed_questions, check_gradable, from_input
from app.assess.scoring import rescore
from app.assess.stats import compute_stats, summarize
from app.assess.store import AssessmentStore, new_paper_id
from app.i18n import request_language, translate
from app.models import Language
from app.slides_html import clean_text

router = APIRouter()
MAX_EXAM_FILES = 10
MAX_UPLOAD_FILES = 120


class Skipped(BaseModel):
    filename: str
    reason: str


class UploadResult(BaseModel):
    assessment: AssessmentView
    added: list[PaperRow]
    skipped: list[Skipped]


class CompareResult(BaseModel):
    a: Paper
    b: Paper
    pair: PairResult | None


class ExportResult(BaseModel):
    url: str
    filename: str


def _store(request: Request) -> AssessmentStore:
    return request.app.state.assessments


def _pipeline(request: Request) -> AssessmentPipeline:
    return request.app.state.assessment_pipeline


def _view(request: Request, a: Assessment) -> AssessmentView:
    """The assessment with its statistics; stored errors (English) in the professor's language."""
    lang = request_language(request)
    view = AssessmentView(**a.model_dump(), stats=compute_stats(a), exam_chars=len(_store(request).exam_text(a.id)))
    for row in view.papers:
        row.error = translate(row.error, lang) if row.error else row.error
    view.rubric.error = translate(view.rubric.error, lang) if view.rubric.error else None
    view.analysis.error = translate(view.analysis.error, lang) if view.analysis.error else None
    return view


def _paper(request: Request, paper: Paper) -> Paper:
    if paper.error:
        paper.error = translate(paper.error, request_language(request))
    return paper


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stem(filename: str) -> str:
    name = re.sub(r"\.(pdf|jpe?g|png)$", "", filename.strip(), flags=re.IGNORECASE)
    return clean_text(name).strip()[:120] or "?"


@router.post("/assessments")
async def create_assessment(
    request: Request,
    title: str = Form(min_length=1, max_length=200),
    course: str = Form("", max_length=200),
    language: Language = Form("el"),
    scale: int = Form(10),
    instructions: str = Form("", max_length=6000),
    exam_text: str = Form("", max_length=60_000),
    exam_files: list[UploadFile] | None = File(None),
) -> AssessmentView:
    store = _store(request)
    title = clean_text(title).strip()
    if not title:
        raise HTTPException(422, "Please give the assessment a title")
    if scale not in (10, 20, 100):
        raise HTTPException(422, "The grade scale must be 10, 20 or 100")
    files = [(f.filename or "exam", await f.read()) for f in exam_files or []]
    files = [(name, data) for name, data in files if data]
    if len(files) > MAX_EXAM_FILES:
        raise HTTPException(422, "Upload at most 10 files for the exam paper")
    for _, data in files:
        if sniff(data) is None:
            raise HTTPException(422, "The exam paper must be PDF, JPG or PNG files")
    a = store.create(title=title, course=clean_text(course).strip(), language=language, scale=scale,
                     instructions=instructions.strip(), exam_text="")
    exam_dir = store.exam_dir(a.id)
    exam_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (_, data) in enumerate(files):
        path = exam_dir / f"e{i + 1:02d}.{sniff(data)}"
        path.write_bytes(data)
        paths.append(path)
    text = await asyncio.to_thread(exam_files_text, paths)
    full = "\n\n".join(p for p in (text, exam_text.strip()) if p)[:60_000]
    (store.assessment_dir(a.id) / "exam.txt").write_text(full, encoding="utf-8")
    _pipeline(request).schedule_pending(a.id)
    return _view(request, store.get(a.id))


@router.get("/assessments")
def list_assessments(request: Request) -> list[AssessmentSummary]:
    return [summarize(a) for a in _store(request).list()]


@router.get("/assessments/{aid}")
def get_assessment(aid: str, request: Request) -> AssessmentView:
    store = _store(request)
    return _view(request, store.get(aid))


@router.patch("/assessments/{aid}")
async def update_assessment(aid: str, body: AssessmentUpdate, request: Request) -> AssessmentView:
    store = _store(request)

    def apply(a: Assessment) -> None:
        if body.title is not None:
            title = clean_text(body.title).strip()
            if not title:
                raise HTTPException(422, "Please give the assessment a title")
            a.title = title
        if body.course is not None:
            a.course = clean_text(body.course).strip()
        if body.instructions is not None:
            a.instructions = body.instructions.strip()
        if body.scale is not None:
            a.scale = body.scale
    await store.mutate(aid, apply)
    return _view(request, await store.refresh_rows(aid))


@router.delete("/assessments/{aid}", status_code=204)
async def delete_assessment(aid: str, request: Request) -> Response:
    store = _store(request)
    store.get(aid)
    await _pipeline(request).cancel_all(aid)
    await store.delete(aid)
    return Response(status_code=204)


# --- Papers -----------------------------------------------------------------------------------------------------

@router.post("/assessments/{aid}/papers")
async def add_papers(aid: str, request: Request, files: list[UploadFile] = File(...),
                     split_every: int | None = Form(None)) -> UploadResult:
    store, lang = _store(request), request_language(request)
    a = store.get(aid)
    if split_every is not None and not 1 <= split_every <= 40:
        raise HTTPException(422, "Split every 1 to 40 pages")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(422, "Upload at most 120 files at a time")
    known = {(store.paper(aid, r.id).sha256, r.filename) for r in a.papers}
    items, skipped = [], []
    for f in files:
        name = (f.filename or "paper").strip() or "paper"
        data = await f.read()
        try:
            uploads = await asyncio.to_thread(split_upload, name, data, split_every)
        except UploadError as exc:
            skipped.append(Skipped(filename=name, reason=translate(str(exc), lang)))
            continue
        for up in uploads:
            digest = hashlib.sha256(up.data).hexdigest()
            if (digest, up.filename) in known:
                skipped.append(Skipped(filename=up.filename, reason=translate("Already uploaded", lang)))
                continue
            known.add((digest, up.filename))
            paper = Paper(id=new_paper_id(), created_at=_now(), filename=up.filename, source=up.kind, sha256=digest,
                          student_name=_stem(up.filename), split_from=name if len(uploads) > 1 else None)
            items.append((paper, up.data))
    a = await store.add_papers(aid, items)
    pipeline = _pipeline(request)
    if not a.paused:
        for paper, _ in items:
            pipeline.schedule_paper(aid, paper.id)
    added = {p.id for p, _ in items}
    return UploadResult(assessment=_view(request, store.get(aid)), added=[r for r in a.papers if r.id in added],
                        skipped=skipped)


@router.get("/assessments/{aid}/papers/{pid}")
def get_paper(aid: str, pid: str, request: Request) -> Paper:
    store = _store(request)
    store.get(aid)
    return _paper(request, store.paper(aid, pid))


@router.patch("/assessments/{aid}/papers/{pid}")
async def update_paper(aid: str, pid: str, body: PaperUpdate, request: Request) -> Paper:
    store = _store(request)
    a = store.get(aid)
    questions = {q.id: q for q in a.rubric.questions}

    def apply(p: Paper) -> None:
        if body.student_name is not None:
            p.student_name, p.name_from = clean_text(body.student_name).strip(), "professor"
        if body.student_id is not None:
            p.student_id, p.name_from = clean_text(body.student_id).strip(), "professor"
        if body.reviewed is not None:
            p.reviewed = body.reviewed
        if body.note is not None:
            p.note = body.note.strip()
        for qid, o in body.results.items():
            index = next((i for i, r in enumerate(p.results) if r.question_id == qid), None)
            if index is None or qid not in questions:
                raise HTTPException(422, "This question has no result yet")
            r = p.results[index].model_copy()
            if o.clear_points:
                r.override_points = None
            elif o.override_points is not None:
                r.override_points = min(o.override_points, questions[qid].points)
            if o.clear_final:
                r.override_final = None
            elif o.override_final is not None:
                r.override_final = o.override_final.strip()
            if o.comment is not None:
                r.comment = o.comment.strip()
            p.results[index] = rescore(questions[qid], r, a.language)
    paper = await store.mutate_paper(aid, pid, apply)
    if body.results:
        await store.mutate(aid, lambda x: setattr(x.analysis, "stale", x.analysis.computed_at is not None))
    return _paper(request, paper)


@router.delete("/assessments/{aid}/papers/{pid}", status_code=204)
async def delete_paper(aid: str, pid: str, request: Request) -> Response:
    store = _store(request)
    store.get(aid)
    store.paper(aid, pid)
    await request.app.state.jobs.cancel([paper_key(aid, pid)])
    await store.remove_paper(aid, pid)
    await store.mutate(aid, lambda x: setattr(x.analysis, "stale", x.analysis.computed_at is not None))
    _pipeline(request).schedule_pending(aid)
    return Response(status_code=204)


@router.post("/assessments/{aid}/papers/{pid}/retry")
async def retry_paper(aid: str, pid: str, request: Request) -> Paper:
    store = _store(request)
    a = store.get(aid)
    if store.paper(aid, pid).status != "failed":
        raise HTTPException(409, "Only a paper that failed can be retried")

    def apply(p: Paper) -> None:
        if p.failed_stage == "grading" and p.reading:
            p.status = "read"
        else:
            p.status, p.pages, p.reading = "queued", [], []
        p.error, p.failed_stage = None, None
    paper = await store.mutate_paper(aid, pid, apply)
    if not a.paused:
        _pipeline(request).schedule_paper(aid, pid)
    return _paper(request, paper)


@router.get("/assessments/{aid}/papers/{pid}/pages/{n}.jpg")
def get_page(aid: str, pid: str, n: int, request: Request) -> FileResponse:
    store = _store(request)
    store.get(aid)
    path = store.pages_dir(aid, pid) / f"p{n:02d}.jpg"
    if not 1 <= n <= 99 or not path.is_file():
        raise HTTPException(404, "Page not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.get("/assessments/{aid}/papers/{pid}/source")
def get_source(aid: str, pid: str, request: Request) -> FileResponse:
    store = _store(request)
    store.get(aid)
    paper = store.paper(aid, pid)
    path = store.source_path(aid, paper)
    media = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}[paper.source]
    filename = paper.filename if paper.filename.lower().endswith(f".{paper.source}") else f"{paper.filename}.{paper.source}"
    return FileResponse(path, media_type=media, filename=filename)


# --- Rubric, analysis, processing -------------------------------------------------------------------------------

@router.put("/assessments/{aid}/rubric")
async def update_rubric(aid: str, body: RubricUpdate, request: Request) -> AssessmentView:
    store = _store(request)
    a = store.get(aid)
    questions = from_input(body.questions, a.rubric.questions)
    if body.confirm and (problem := check_gradable(questions)):
        raise HTTPException(422, problem)
    changed = changed_questions(a.rubric.questions, questions)
    removed = {q.id for q in a.rubric.questions} - {q.id for q in questions}

    if body.confirm:
        for q in questions:
            if q.key_from == "lara":
                q.key_from = "professor"  # the professor saw the "check it" badge and chose to grade with the key

    def apply(x: Assessment) -> None:
        x.rubric.questions = questions
        x.rubric.error = None
        if body.confirm:
            x.rubric.version += 1
            x.rubric.status = "confirmed"
        else:
            x.rubric.status = "draft"
        x.analysis.stale = x.analysis.computed_at is not None
    await store.mutate(aid, apply)
    if body.confirm and (changed or removed):
        # Marks and corrected readings on questions whose marking changed no longer apply.
        for row in store.get(aid).papers:
            paper = store.paper(aid, row.id)
            if not paper.results:
                continue

            def clean(p: Paper) -> None:
                kept = []
                for r in p.results:
                    if r.question_id in removed:
                        continue
                    if r.question_id in changed:
                        r = r.model_copy(update={"override_points": None, "override_final": None})
                    kept.append(r)
                p.results = kept
            await store.mutate_paper(aid, row.id, clean)
    await store.refresh_rows(aid)
    if body.confirm:
        _pipeline(request).schedule_pending(aid)
    return _view(request, store.get(aid))


@router.post("/assessments/{aid}/rubric/draft")
async def draft_rubric(aid: str, request: Request) -> AssessmentView:
    store = _store(request)
    a = store.get(aid)
    if a.rubric.status == "drafting":
        raise HTTPException(409, "Lara is already drafting the rubric")
    if not store.exam_text(aid).strip() and not store.exam_files(aid) and \
            not any(r.status in ("read", "graded") for r in a.papers):
        raise HTTPException(422, "Add the exam paper or wait until a paper has been read")
    await store.mutate(aid, lambda x: setattr(x.rubric, "status", "drafting"))
    _pipeline(request).schedule_rubric(aid)
    return _view(request, store.get(aid))


@router.post("/assessments/{aid}/analysis")
async def rerun_analysis(aid: str, request: Request) -> AssessmentView:
    store = _store(request)
    a = store.get(aid)
    if sum(1 for r in a.papers if r.status == "graded") < 2:
        raise HTTPException(422, "The class analysis needs at least two graded papers")
    await store.mutate(aid, lambda x: setattr(x.analysis, "stale", True))
    _pipeline(request).schedule_class(aid)
    return _view(request, store.get(aid))


@router.post("/assessments/{aid}/pause")
async def pause(aid: str, request: Request) -> AssessmentView:
    store = _store(request)
    store.get(aid)
    await _pipeline(request).pause(aid)
    return _view(request, store.get(aid))


@router.post("/assessments/{aid}/resume")
async def resume(aid: str, request: Request) -> AssessmentView:
    store = _store(request)
    store.get(aid)
    await _pipeline(request).resume(aid)
    return _view(request, store.get(aid))


@router.get("/assessments/{aid}/compare/{a_id}/{b_id}")
def compare(aid: str, a_id: str, b_id: str, request: Request) -> CompareResult:
    store = _store(request)
    a = store.get(aid)
    pa, pb = store.paper(aid, a_id), store.paper(aid, b_id)
    key = (min(a_id, b_id), max(a_id, b_id))
    pair = next((p for p in a.analysis.pairs if (p.a, p.b) == key), None)
    return CompareResult(a=_paper(request, pa), b=_paper(request, pb), pair=pair)


# --- Export -----------------------------------------------------------------------------------------------------

@router.post("/assessments/{aid}/export")
async def export(aid: str, body: ExportRequest, request: Request) -> ExportResult:
    store = _store(request)
    a = store.get(aid)
    papers = store.papers(aid)
    try:
        path, filename = await asyncio.to_thread(export_assessment, store.export_dir(aid), a, papers, body.format)
    except Exception as exc:  # noqa: BLE001 - a broken font or file must reach the UI as a readable error
        raise HTTPException(502, f"Export failed: {exc}") from exc
    path.with_name(path.name + ".name").write_text(filename, encoding="utf-8")
    return ExportResult(url=f"/assessments/{aid}/export/{path.name}?v={uuid.uuid4().hex[:8]}", filename=filename)


@router.get("/assessments/{aid}/export/{file}")
def download_export(aid: str, file: str, request: Request) -> FileResponse:
    store = _store(request)
    store.get(aid)
    path = store.export_dir(aid) / file
    suffix = path.suffix.lstrip(".")
    if "/" in file or suffix not in MEDIA_TYPES or not path.is_file():
        raise HTTPException(404, "Export not found")
    name_file = path.with_name(path.name + ".name")
    filename = name_file.read_text(encoding="utf-8") if name_file.is_file() else file
    return FileResponse(path, media_type=MEDIA_TYPES[suffix], filename=filename)
