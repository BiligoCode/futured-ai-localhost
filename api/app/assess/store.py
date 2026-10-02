"""Assessments on disk (design §4).

    data/assessments/<aid>/assessment.json   settings, rubric, one row per paper
    data/assessments/<aid>/analysis.json     the class analysis (kept apart: it is large and changes rarely)
    data/assessments/<aid>/exam.txt, exam/   the exam paper / answer key
    data/assessments/<aid>/papers/<pid>/     source file, paper.json, pages/

Every write is atomic (.tmp + os.replace). A paper and its row in assessment.json change together under the
assessment's lock, so the list views never disagree with the paper pages."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.assess.models import Analysis, Assessment, AssessmentNotFound, Paper, PaperNotFound
from app.assess.scoring import build_row

__all__ = ["AssessmentNotFound", "AssessmentStore", "PaperNotFound", "new_paper_id"]

_AID = re.compile(r"^[0-9a-f]{10}$")
_PID = re.compile(r"^[0-9a-f]{8}$")
INTERRUPTED = "Interrupted by server restart"


def new_paper_id() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class AssessmentStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / "assessments"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # --- paths ------------------------------------------------------------------------------------------------

    def assessment_dir(self, aid: str) -> Path:
        if not _AID.fullmatch(aid or ""):
            raise AssessmentNotFound(aid)
        return self.dir / aid

    def exam_dir(self, aid: str) -> Path:
        return self.assessment_dir(aid) / "exam"

    def paper_dir(self, aid: str, pid: str) -> Path:
        if not _PID.fullmatch(pid or ""):
            raise PaperNotFound(pid)
        return self.assessment_dir(aid) / "papers" / pid

    def pages_dir(self, aid: str, pid: str) -> Path:
        return self.paper_dir(aid, pid) / "pages"

    def source_path(self, aid: str, paper: Paper) -> Path:
        return self.paper_dir(aid, paper.id) / f"source.{paper.source}"

    def export_dir(self, aid: str) -> Path:
        d = self.assessment_dir(aid) / "export"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def lock(self, aid: str) -> asyncio.Lock:
        return self._locks[aid]

    # --- assessments ------------------------------------------------------------------------------------------

    def create(self, *, title: str, course: str, language: str, scale: int, instructions: str,
               exam_text: str) -> Assessment:
        now = _now()
        a = Assessment(id=uuid.uuid4().hex[:10], created_at=now, updated_at=now, title=title, course=course,
                       language=language, scale=scale, instructions=instructions)
        d = self.dir / a.id
        (d / "papers").mkdir(parents=True)
        (d / "exam.txt").write_text(exam_text, encoding="utf-8")
        self.write(a)
        self.write_analysis(a.id, a.analysis)
        return a

    def get(self, aid: str) -> Assessment:
        path = self.assessment_dir(aid) / "assessment.json"
        if not path.is_file():
            raise AssessmentNotFound(aid)
        a = Assessment.model_validate_json(path.read_text(encoding="utf-8"))
        analysis = path.with_name("analysis.json")
        if analysis.is_file():
            a.analysis = Analysis.model_validate_json(analysis.read_text(encoding="utf-8"))
        return a

    def list(self) -> list[Assessment]:
        out = []
        for d in self.dir.iterdir():
            if (d / "assessment.json").is_file():
                try:
                    out.append(self.get(d.name))
                except AssessmentNotFound:
                    continue
        return sorted(out, key=lambda a: a.created_at, reverse=True)

    def exam_text(self, aid: str) -> str:
        path = self.assessment_dir(aid) / "exam.txt"
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def exam_files(self, aid: str) -> list[Path]:
        d = self.exam_dir(aid)
        return sorted(p for p in d.iterdir() if p.is_file()) if d.is_dir() else []

    def write(self, a: Assessment) -> None:
        _write_atomic(self.assessment_dir(a.id) / "assessment.json", a.model_dump_json(indent=1, exclude={"analysis"}))

    def write_analysis(self, aid: str, analysis: Analysis) -> None:
        _write_atomic(self.assessment_dir(aid) / "analysis.json", analysis.model_dump_json())

    async def mutate(self, aid: str, fn: Callable[[Assessment], None]) -> Assessment:
        async with self._locks[aid]:
            return self._mutate(aid, fn)

    def _mutate(self, aid: str, fn: Callable[[Assessment], None]) -> Assessment:
        a = self.get(aid)
        before = a.analysis.model_dump_json()
        fn(a)
        a.updated_at = _now()
        self.write(a)
        if a.analysis.model_dump_json() != before:
            self.write_analysis(aid, a.analysis)
        return a

    async def refresh_rows(self, aid: str) -> Assessment:
        """Rebuild every paper row (after the rubric, the scale or the class analysis changed)."""
        async with self._locks[aid]:
            def apply(a: Assessment) -> None:
                papers = {p.id: p for p in self._papers(aid, a)}
                a.papers = [build_row(papers[r.id], a) if r.id in papers else r for r in a.papers]
            return self._mutate(aid, apply)

    async def delete(self, aid: str) -> None:
        self.get(aid)
        async with self._locks[aid]:
            shutil.rmtree(self.assessment_dir(aid), ignore_errors=True)
        self._locks.pop(aid, None)

    # --- papers -----------------------------------------------------------------------------------------------

    def paper(self, aid: str, pid: str) -> Paper:
        path = self.paper_dir(aid, pid) / "paper.json"
        if not path.is_file():
            raise PaperNotFound(pid)
        return Paper.model_validate_json(path.read_text(encoding="utf-8"))

    def _papers(self, aid: str, a: Assessment) -> list[Paper]:
        out = []
        for row in a.papers:
            try:
                out.append(self.paper(aid, row.id))
            except PaperNotFound:
                continue
        return out

    def papers(self, aid: str) -> list[Paper]:
        return self._papers(aid, self.get(aid))

    def write_paper(self, aid: str, paper: Paper) -> None:
        _write_atomic(self.paper_dir(aid, paper.id) / "paper.json", paper.model_dump_json(indent=1))

    async def add_papers(self, aid: str, items: list[tuple[Paper, bytes]]) -> Assessment:
        async with self._locks[aid]:
            def apply(a: Assessment) -> None:
                for paper, data in items:
                    d = self.paper_dir(aid, paper.id)
                    (d / "pages").mkdir(parents=True)
                    (d / f"source.{paper.source}").write_bytes(data)
                    paper.updated_at = _now()
                    self.write_paper(aid, paper)
                    a.papers.append(build_row(paper, a))
                if items:
                    a.analysis.stale = a.analysis.computed_at is not None or a.analysis.stale
            return self._mutate(aid, apply)

    async def mutate_paper(self, aid: str, pid: str, fn: Callable[[Paper], None]) -> Paper:
        async with self._locks[aid]:
            paper = self.paper(aid, pid)
            fn(paper)
            paper.updated_at = _now()
            self.write_paper(aid, paper)

            def apply(a: Assessment) -> None:
                row = build_row(paper, a)
                a.papers = [row if r.id == pid else r for r in a.papers]
            self._mutate(aid, apply)
            return paper

    async def remove_paper(self, aid: str, pid: str) -> None:
        self.paper(aid, pid)
        async with self._locks[aid]:
            def apply(a: Assessment) -> None:
                a.papers = [r for r in a.papers if r.id != pid]
                a.analysis.pairs = [p for p in a.analysis.pairs if pid not in (p.a, p.b)]
                a.analysis.covered = [c for c in a.analysis.covered if c != pid]
                for c in a.analysis.clusters:
                    c.members = [m for m in c.members if m != pid]
                a.analysis.clusters = [c for c in a.analysis.clusters if len(c.members) >= 2]
            self._mutate(aid, apply)
            shutil.rmtree(self.paper_dir(aid, pid), ignore_errors=True)

    # --- recovery ---------------------------------------------------------------------------------------------

    def reset_busy(self, aid: str) -> Assessment:
        """Nothing is running any more (cancelled, or the server restarted): reading → queued, grading → read,
        a rubric being drafted → none, a running class analysis → idle and stale. Finished work is kept."""
        a = self.get(aid)
        for paper in self._papers(aid, a):
            if paper.status not in ("reading", "grading"):
                continue
            if paper.status == "reading":
                paper.status, paper.pages, paper.reading = "queued", [], []
            else:
                paper.status = "read"
            paper.updated_at = _now()
            self.write_paper(aid, paper)
            a.papers = [build_row(paper, a) if r.id == paper.id else r for r in a.papers]
        if a.rubric.status == "drafting":
            a.rubric.status = "draft" if a.rubric.questions else "none"
        if a.analysis.status == "running":
            a.analysis.status, a.analysis.stale = "idle", True
        a.updated_at = _now()
        self.write(a)
        self.write_analysis(aid, a.analysis)
        return a

    async def reset(self, aid: str) -> Assessment:
        async with self._locks[aid]:
            return self.reset_busy(aid)

    def reset_all(self) -> list[Assessment]:
        return [self.reset_busy(a.id) for a in self.list()]
