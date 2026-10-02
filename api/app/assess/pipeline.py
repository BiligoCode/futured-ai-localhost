"""Background work for assessments (design §5): reading and grading papers, drafting the rubric, the class analysis.

Jobs run on the app's JobRunner, one per paper (`asmt:<aid>:<pid>`, coalesced so a rubric change during grading
re-grades once more), one rubric draft (`asmt-rubric:<aid>`) and one class analysis (`asmt-class:<aid>`). Every model
call takes a slot of one global semaphore; rendering and forensics take a CPU slot."""
import asyncio
import logging
from pathlib import Path
from typing import Callable

from app.assess.classwork import run_class_analysis
from app.assess.forensics import PdfFacts, analyze_image, analyze_pdf, author_mismatch
from app.assess.grading import grade_paper, merge_overrides, second_reading
from app.assess.ingest import UploadError, exam_images, letters, page_image, render_pages
from app.assess.models import DEFINITIVE, Assessment, AssessmentNotFound, Paper, PaperNotFound, PageReading
from app.assess.reading import printed_check, read_page, reading_text, student_identity
from app.assess.rubric import draft_from_images, draft_from_papers, draft_from_text
from app.assess.signals import ai_analysis, finish, student_text
from app.assess.store import AssessmentStore
from app.jobs import JobRunner
from app.llm import LLM, VisionLLM

log = logging.getLogger(__name__)
CPU_SLOTS = 4
EXAM_TEXT_LETTERS = 150  # below this the exam paper is treated as scanned and read with the vision model
PAPERS_FOR_RUBRIC = 3
UNREADABLE_PAGE = {"el": "Η σελίδα δεν μπόρεσε να διαβαστεί.", "en": "This page could not be read."}


def paper_key(aid: str, pid: str) -> str:
    return f"asmt:{aid}:{pid}"


def needs_work(a: Assessment, status: str, rubric_version: int) -> bool:
    if status in ("queued", "reading"):
        return True
    confirmed = a.rubric.status == "confirmed"
    return confirmed and (status in ("read", "grading") or (status == "graded" and rubric_version != a.rubric.version))


def settled(a: Assessment) -> bool:
    return not any(needs_work(a, r.status, r.rubric_version) for r in a.papers)


class AssessmentPipeline:
    def __init__(self, store: AssessmentStore, jobs: JobRunner, *, vision: VisionLLM, verifier: VisionLLM | None,
                 grader: LLM, concurrency: int = 6):
        self.store = store
        self.jobs = jobs
        self.vision = vision
        self.verifier = verifier
        self.grader = grader
        self.model_slots = asyncio.Semaphore(concurrency)
        self.cpu_slots = asyncio.Semaphore(CPU_SLOTS)

    async def call(self, fn: Callable, *args, **kwargs):
        async with self.model_slots:
            return await asyncio.to_thread(fn, *args, **kwargs)

    # --- scheduling -------------------------------------------------------------------------------------------

    def schedule_paper(self, aid: str, pid: str) -> None:
        self.jobs.submit_coalesced(paper_key(aid, pid), lambda: self._paper_job(aid, pid))

    def schedule_pending(self, aid: str) -> None:
        a = self.store.get(aid)
        if a.paused:
            return
        for row in a.papers:
            if needs_work(a, row.status, row.rubric_version):
                self.schedule_paper(aid, row.id)
        self._maybe_follow_up(a)

    def schedule_rubric(self, aid: str) -> None:
        self.jobs.submit(f"asmt-rubric:{aid}", lambda: self._draft_job(aid))

    def schedule_class(self, aid: str) -> None:
        self.jobs.submit_coalesced(f"asmt-class:{aid}", lambda: self._class_job(aid))

    def keys(self, aid: str) -> list[str]:
        return self.jobs.keys(f"asmt:{aid}:") + [f"asmt-rubric:{aid}", f"asmt-class:{aid}"]

    async def cancel_all(self, aid: str) -> None:
        await self.jobs.cancel(self.keys(aid))

    async def pause(self, aid: str) -> None:
        await self.store.mutate(aid, lambda a: setattr(a, "paused", True))
        await self.cancel_all(aid)
        await self.store.reset(aid)

    async def resume(self, aid: str) -> None:
        await self.store.mutate(aid, lambda a: setattr(a, "paused", False))
        self.schedule_pending(aid)

    async def recover(self) -> None:
        """After a restart nothing is running: reset half-done work, rebuild the paper rows (so lists made by an
        older version show everything) and start the unpaused assessments again."""
        for a in self.store.reset_all():
            try:
                await self.store.refresh_rows(a.id)
                if not a.paused:
                    self.schedule_pending(a.id)
            except AssessmentNotFound:
                continue

    def _maybe_follow_up(self, a: Assessment) -> None:
        """Start what the state calls for: a rubric drafted from the first papers, or the class analysis."""
        if a.paused:
            return
        if a.rubric.status == "none" and not a.rubric.questions:
            has_exam = letters(self.store.exam_text(a.id)) >= EXAM_TEXT_LETTERS or bool(self.store.exam_files(a.id))
            read = [r for r in a.papers if r.status in ("read", "graded")]
            if has_exam or (a.papers and len(read) >= min(PAPERS_FOR_RUBRIC, len(a.papers))):
                self.schedule_rubric(a.id)
        graded = {r.id for r in a.papers if r.status == "graded" and r.rubric_version == a.rubric.version}
        if a.rubric.status == "confirmed" and settled(a) and len(graded) >= 2 and a.analysis.status != "running" and \
                (a.analysis.stale or set(a.analysis.covered) != graded or a.analysis.computed_at is None):
            self.schedule_class(a.id)

    # --- jobs -------------------------------------------------------------------------------------------------

    async def _paper_job(self, aid: str, pid: str) -> None:
        try:
            a, p = self.store.get(aid), self.store.paper(aid, pid)
        except (AssessmentNotFound, PaperNotFound):
            return
        if a.paused:
            return
        if p.status in ("queued", "reading"):
            if not await self._read(aid, pid):
                self._after(aid)
                return
        a, p = self.store.get(aid), self.store.paper(aid, pid)
        if a.rubric.status == "confirmed" and needs_work(a, p.status, p.rubric_version):
            await self._grade(aid, pid)
        self._after(aid)

    def _after(self, aid: str) -> None:
        try:
            self._maybe_follow_up(self.store.get(aid))
        except AssessmentNotFound:
            pass

    async def _fail(self, aid: str, pid: str, stage: str, message: str) -> None:
        def apply(p: Paper) -> None:
            p.status, p.failed_stage, p.error = "failed", stage, message[:500]
        await self.store.mutate_paper(aid, pid, apply)

    async def _read(self, aid: str, pid: str) -> bool:
        def start(p: Paper) -> None:
            p.status, p.error, p.failed_stage = "reading", None, None
        paper = await self.store.mutate_paper(aid, pid, start)
        source = self.store.source_path(aid, paper)
        pages_dir = self.store.pages_dir(aid, pid)
        paper_language = "el" if self.store.get(aid).language == "el" else "en"
        try:
            async with self.cpu_slots:
                rendered = await asyncio.to_thread(render_pages, source, paper.source, pages_dir)
                if paper.source == "pdf":
                    facts = await asyncio.to_thread(analyze_pdf, source, rendered)
                else:
                    facts = PdfFacts(await asyncio.to_thread(analyze_image, source, paper.source), methods={1: "vision"})
            pages = [r.info.model_copy(update={"method": facts.methods.get(r.info.n, r.info.method)}) for r in rendered]
            del rendered
            readings: dict[int, PageReading] = {n: PageReading(n=n, text=t) for n, t in facts.visible_text.items()}
            vision_pages = [pg.n for pg in pages if pg.method == "vision"]
            replies = await asyncio.gather(*(self.call(read_page, self.vision, page_image(pages_dir, n), n, len(pages))
                                             for n in vision_pages), return_exceptions=True)
            identities = []
            failed = 0
            for n, reply in zip(vision_pages, replies):
                if isinstance(reply, BaseException):
                    log.warning("page %s of paper %s could not be read: %s", n, pid, reply)
                    failed += 1
                    readings[n] = PageReading(n=n, notes=UNREADABLE_PAGE[paper_language])
                else:
                    readings[n], name, sid = reply
                    identities.append((name, sid))
            if vision_pages and failed == len(vision_pages) and not facts.visible_text:
                error = next(r for r in replies if isinstance(r, BaseException))
                raise RuntimeError(str(error))
        except asyncio.CancelledError:
            raise
        except UploadError as exc:
            await self._fail(aid, pid, "reading", str(exc))
            return False
        except Exception as exc:  # noqa: BLE001 - shown on the paper with Retry
            log.exception("reading paper %s failed", pid)
            await self._fail(aid, pid, "reading", f"Reading the paper failed: {exc}")
            return False
        name, sid = student_identity(identities)

        def done(p: Paper) -> None:
            p.pages = pages
            p.reading = [readings[n] for n in sorted(readings)]
            p.forensics = facts.forensics
            p.sha256 = facts.forensics.sha256 or p.sha256
            if p.name_from == "file" and (name or sid):
                p.student_name = name or p.student_name
                p.student_id = sid or p.student_id
                p.name_from = "paper"
            p.status = "read"
        await self.store.mutate_paper(aid, pid, done)
        return True

    async def _grade(self, aid: str, pid: str) -> None:
        def start(p: Paper) -> None:
            p.status, p.error, p.failed_stage = "grading", None, None
        paper = await self.store.mutate_paper(aid, pid, start)
        a = self.store.get(aid)
        version = a.rubric.version
        questions = a.rubric.questions
        try:
            reference = "\n".join([self.store.exam_text(aid), *(q.prompt for q in questions)])
            transcript = reading_text(paper.reading, printed=printed_check(reference))
            outcome = await self.call(grade_paper, self.grader, a, transcript)
            results = merge_overrides(paper.results, outcome.results, set(), questions, a.language)
            vision_pages = [pg.n for pg in paper.pages if pg.method == "vision"]
            if self.verifier is not None and vision_pages and any(q.type in DEFINITIVE for q in questions):
                pages_dir = self.store.pages_dir(aid, pid)
                images = {n: page_image(pages_dir, n) for n in vision_pages}
                results = await self.call(second_reading, self.verifier, a, paper, results, images)
            text, typed = student_text(paper, self.store.exam_text(aid))
            ai = ai_analysis(text, typed, outcome.ai_likelihood, outcome.ai_reasons)
            if paper.ai is not None:  # keep the class-relative signals until the class analysis runs again
                kept = [s for s in paper.ai.signals if s.code in ("over_elaborate", "lara_vs_class")]
                if kept:
                    ai.signals = [s for s in ai.signals if not (s.code == "lara_reading" and any(k.code == "lara_vs_class" for k in kept))]
                    ai.signals.extend(kept)
                    ai = finish(ai)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - shown on the paper with Retry
            log.exception("grading paper %s failed", pid)
            await self._fail(aid, pid, "grading", f"Grading failed: {exc}")
            return

        def done(p: Paper) -> None:
            # Overrides the professor made while the model was grading are in p.results: keep them.
            p.results = merge_overrides(p.results, results, set(), questions, a.language)
            p.summary = outcome.summary
            p.ai = ai
            p.rubric_version = version
            if p.name_from == "file" and (outcome.student_name or outcome.student_id):
                p.student_name = outcome.student_name or p.student_name
                p.student_id = outcome.student_id or p.student_id
                p.name_from = "paper"
            if p.forensics is not None and not any(f.code == "author_mismatch" for f in p.forensics.findings):
                if (finding := author_mismatch(p.forensics, p.student_name)) is not None:
                    p.forensics.findings.append(finding)
            p.status = "graded"
        await self.store.mutate_paper(aid, pid, done)
        if self.store.get(aid).rubric.version != version:
            self.schedule_paper(aid, pid)  # the rubric changed while grading: once more with the new one

    async def _draft_job(self, aid: str) -> None:
        try:
            a = self.store.get(aid)
        except AssessmentNotFound:
            return

        def start(x: Assessment) -> None:
            x.rubric.status, x.rubric.error = "drafting", None
        await self.store.mutate(aid, start)
        exam_text = self.store.exam_text(aid)
        files = self.store.exam_files(aid)
        try:
            if letters(exam_text) >= EXAM_TEXT_LETTERS:
                questions, note = await self.call(draft_from_text, self.grader, exam_text, a.language, title=a.title)
                source = "exam"
            elif files:
                images = await asyncio.to_thread(exam_images, files)
                questions, note = await self.call(draft_from_images, self.vision, images, a.language, title=a.title,
                                                  exam_text=exam_text)
                source = "exam"
            else:
                papers = [p for p in self.store.papers(aid) if p.status in ("read", "graded")][:PAPERS_FOR_RUBRIC]
                if not papers:
                    raise RuntimeError("no paper has been read yet")
                questions, note = await self.call(draft_from_papers, self.grader,
                                                  [reading_text(p.reading, show_printed=True) for p in papers], a.language,
                                                  title=a.title)
                source = "papers"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the professor can write the rubric or ask again
            log.exception("drafting the rubric of %s failed", aid)
            message = str(exc)[:500]

            def failed(x: Assessment) -> None:
                if x.rubric.status == "drafting":
                    x.rubric.status = "failed"
                    x.rubric.error = message if message.startswith("Could not draft") else f"Could not draft a rubric: {message}"
            await self.store.mutate(aid, failed)
            return

        def done(x: Assessment) -> None:
            if x.rubric.status != "drafting":
                return  # the professor saved their own rubric meanwhile
            x.rubric.questions, x.rubric.note, x.rubric.source, x.rubric.status = questions, note, source, "draft"
        await self.store.mutate(aid, done)

    async def _class_job(self, aid: str) -> None:
        try:
            a = self.store.get(aid)
        except AssessmentNotFound:
            return
        if a.paused or not settled(a):
            await self.store.mutate(aid, lambda x: setattr(x.analysis, "stale", True))
            return
        await run_class_analysis(self.store, aid, self.grader, self.call)


def exam_files_text(paths: list[Path]) -> str:
    """Text of uploaded exam PDFs (empty for scans)."""
    from app.ingest import EmptyMaterialError, extract_pdf_text

    parts = []
    for path in paths:
        if path.suffix.lower() != ".pdf":
            continue
        try:
            parts.append(extract_pdf_text(path.read_bytes()).strip())
        except EmptyMaterialError:
            continue
    return "\n\n".join(p for p in parts if p)
