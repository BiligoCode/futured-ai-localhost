"""The class analysis (design §6.6, §7, §8): clusters of shared mistakes and details, the copying pairs (checked side
by side by the model), the class-relative AI signal, and the class insights.

It runs once every paper is settled, and again whenever papers or marks change; it never touches marks."""
import asyncio
import logging
import re
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.assess.ingest import load_ink
from app.assess.models import DEFINITIVE, Analysis, Assessment, Cluster, Paper, PairResult, Question, SharedItem
from app.assess.signals import student_text, with_class_signal
from app.assess.similarity import (CONTENT, CohortPaper, apply_verdict, class_outliers, corroborated, example_clusters,
                                   final_value, find_quote, gram_counts, pair_results, shared_rarely)
from app.assess.stats import compute_stats
from app.assess.store import AssessmentStore
from app.llm import LLM
from app.parsing import extract_json
from app.storyboard import language_name

log = logging.getLogger(__name__)
Call = Callable[..., Awaitable]
MAX_PAIR_CHECKS = 15     # at least; one per three papers in larger classes
GROUPING_CALLS = 2       # the grouping misses a real group about one call in three: two calls, their union
PAIR_CHECK_FROM = 25
RARE_QUOTE_PAPERS = 2  # words a third paper of the class also uses are not evidence against these two
KEEP_PAIRS_FROM = 10
MAX_PAIRS = 400

SYSTEM = "You help a university professor analyse a class's exam papers. You are careful and fair. Reply with only JSON."

CLUSTER_PROMPT = """Exam question {label}: {prompt}

For each paper, the specific mistakes and the distinctive details noted while grading this question:
{items}

Group the papers that share the SAME specific wrong claim, or the SAME distinctive detail (the same made-up example \
values, the same unusual phrase or method). The same wrong claim noted in different words is one group, and a mistake \
noted as its correction ("the worst case is not only …") is still the student's wrong claim, not an omission. Only \
group content that is genuinely the same and unlikely to be written independently. Never group: omissions (a step or explanation that is missing), general qualities (brief, informal, \
vague), standard textbook content many students would write, or conventional choices any student might make (the usual \
starting point or variant of a method, a small round example number, the textbook's own example). Groups need at least two \
papers; most papers belong to no group, and "groups": [] is a normal answer.

Reply with only JSON: {{"groups": [{{"kind": "mistake" | "detail", "label": "<short description, written in {language} (translate if needed)>", "members": ["P3", "P7"]}}]}}"""

PAIR_PROMPT = """Exam: {title}

Two students' papers, question by question. What an automatic comparison found:
{evidence}

{answers}

Decide whether these papers were written independently. Students who studied the same lectures write similar \
things; that alone is not copying, and neither is a conventional choice (the usual variant of a method, a common \
example number).
- "likely_copied": the similarity cannot reasonably come from independent work (identical unusual wording, the \
same idiosyncratic mistakes or examples, the same structure beyond what the questions force).
- "possibly": suggestive, but it could be coincidence or studying together.
- "independent": the overlap is what the questions or the course material naturally produce.

In "shared", list each specific thing both papers have that independent students would be unlikely to share — \
the same unusual example, the same specific mistake, the same unusual wording — with each paper's own words copied \
exactly (a phrase of at least three words, at most one sentence). Leave out what the question, the course or common \
sense makes many students write; "shared": [] is a normal answer.

Reply with only JSON: {{"verdict": "likely_copied" | "possibly" | "independent", "explanation": "<2–3 sentences in \
{language} citing the specific evidence>", "shared": [{{"question": "<question label>", "what": "<a few words in \
{language}>", "a": "<paper A's exact words>", "b": "<paper B's exact words>"}}]}}"""

INSIGHTS_PROMPT = """Exam: {title}{course}
{n} papers graded. Average {mean} / {scale}, median {median}, pass rate {pass_rate}.

Questions (average share of the points; correct answers for questions with a definitive answer):
{questions}

Shared mistakes found (number of students):
{clusters}

Write a short class report for the professor.
Reply with only JSON: {{"insights": "<one paragraph in {language}: how the class did, what was mastered, what was not>",
 "recommendations": ["<2–4 concrete teaching suggestions in {language}>"],
 "questions": {{"<question id>": "<one sentence in {language} about that question>"}}}}"""


class _Group(BaseModel):
    kind: str = "mistake"
    label: str = ""
    members: list[str] = Field(default_factory=list)

    @field_validator("members", mode="before")
    @classmethod
    def _m(cls, v):
        return [str(x) for x in (v or [])]


class _Groups(BaseModel):
    groups: list[_Group] = Field(default_factory=list)


class _Shared(BaseModel):
    question: str = ""
    what: str = ""
    a: str = ""
    b: str = ""


class _Verdict(BaseModel):
    verdict: str = ""
    explanation: str = ""
    shared: list[_Shared] = Field(default_factory=list)


class _Insights(BaseModel):
    insights: str = ""
    recommendations: list[str] = Field(default_factory=list)
    questions: dict[str, str] = Field(default_factory=dict)

    @field_validator("recommendations", mode="before")
    @classmethod
    def _r(cls, v):
        if isinstance(v, str):
            return [v]
        return [str(x) for x in (v or [])]

    @field_validator("questions", mode="before")
    @classmethod
    def _q(cls, v):
        return {str(k): str(x) for k, x in (v or {}).items()} if isinstance(v, dict) else {}


def _ask(llm: LLM, prompt: str, model: type[BaseModel]):
    messages = [{"role": "user", "content": prompt}]
    error = ""
    for _ in range(2):
        reply = llm(SYSTEM, messages)
        try:
            return model.model_validate(extract_json(reply))
        except (ValueError, ValidationError) as exc:
            error = str(exc)[:300]
            messages = messages + [{"role": "assistant", "content": reply},
                                   {"role": "user", "content": f"Your previous reply was not valid: {error}. Reply with only the JSON."}]
    raise ValueError(error)


_PDF_DATE = re.compile(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?")


def parse_date(value: str) -> datetime | None:
    """A PDF date ("D:20260212103000+02'00'") or an ISO date, in UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    m = _PDF_DATE.match(value.strip())
    if not m or not m.group(2):
        return None
    y, mo, d, h, mi, sec = (int(g) if g else default for g, default in zip(m.groups()[:6], (0, 1, 1, 0, 0, 0)))
    try:
        dt = datetime(y, mo, d, h, mi, sec)
    except ValueError:
        return None
    sign, oh, om = m.group(7), int(m.group(8) or 0), int(m.group(9) or 0)
    offset = timedelta(hours=oh, minutes=om)
    if sign == "+":
        dt -= offset
    elif sign == "-":
        dt += offset
    return dt.replace(tzinfo=timezone.utc)


def cohort_paper(store: AssessmentStore, aid: str, paper: Paper, questions: list[Question], exam_text: str) -> CohortPaper:
    by_id = {q.id: q for q in questions}
    answers, finals, skipped = {}, {}, set()
    for r in paper.results:
        q = by_id.get(r.question_id)
        if q is None:
            continue
        if r.status == "unanswered":
            skipped.add(q.id)
        if q.type in ("open", "short", "numeric") and r.answer:
            answers[q.id] = r.answer
        if q.type in DEFINITIVE:
            value = final_value(q, r.override_final if r.override_final is not None else r.final)
            if value is not None and r.correct is not None:
                finals[q.id] = (value, bool(r.correct))
    pages_dir = store.pages_dir(aid, paper.id)
    f = paper.forensics
    created = None
    if f is not None:
        created = parse_date(f.metadata.get("CreationDate", "")) or parse_date(f.xmp.get("CreateDate", ""))
    return CohortPaper(
        id=paper.id, name=paper.student_name, answers=answers, finals=finals, skipped=skipped,
        style_text=student_text(paper, exam_text)[0],
        # Only handwritten/scanned pages: typed pages all look alike at this resolution (lines of text).
        pages=[(pg.n, pg.dhash, load_ink(pages_dir, pg.n)) for pg in paper.pages if pg.method == "vision"],
        kind=f.kind if f else "scanned", split=paper.split_from is not None, sha256=paper.sha256,
        file_id=f.file_id if f else None, document_id=(f.xmp.get("DocumentID") if f else None) or None,
        author=(f.metadata.get("Author") or f.xmp.get("Creator") or "") if f else "", created=created,
    )


async def _clusters(llm: LLM, call: Call, a: Assessment, papers: list[Paper]) -> list[Cluster]:
    language = language_name(a.language)
    tasks = []
    for q in a.rubric.questions:
        # Open questions only: identical wrong finals on the others are judged against chance (same_wrong_answers).
        if q.type != "open":
            continue
        items, index = [], {}
        for i, p in enumerate(papers):
            r = p.result(q.id)
            if r is None or not (r.errors or r.specifics):
                continue
            tag = f"P{i + 1}"
            index[tag] = p.id
            items.append(f"{tag}: mistakes: {'; '.join(r.errors) or '—'} | details: {'; '.join(r.specifics) or '—'}")
        if len(items) < 2:
            continue
        prompt = CLUSTER_PROMPT.format(label=q.label, prompt=q.prompt[:400] or "—", items="\n".join(items), language=language)
        tasks.extend((q, index, call(_ask, llm, prompt, _Groups)) for _ in range(GROUPING_CALLS))
    found: list[Cluster] = []
    results = await asyncio.gather(*(t[2] for t in tasks), return_exceptions=True)
    for (q, index, _), result in zip(tasks, results):
        if isinstance(result, BaseException):
            log.warning("clustering failed for question %s: %s", q.label, result)
            continue
        for g in result.groups:
            members = sorted({index[m.strip().upper()] for m in g.members if m.strip().upper() in index})
            if len(members) >= 2 and g.label.strip():
                found.append(Cluster(question_id=q.id, kind="detail" if g.kind == "detail" else "mistake",
                                     label=g.label.strip()[:200], members=members))
    return merge_clusters(found)


def merge_clusters(found: list[Cluster]) -> list[Cluster]:
    """One group per shared thing: groups of the same kind on the same question that share two or more papers are
    the same group seen twice (by the two calls, or labelled differently) — merged, so no pair counts it twice."""
    merged: list[Cluster] = []
    for c in found:
        same = next((m for m in merged if m.question_id == c.question_id and m.kind == c.kind
                     and len(set(m.members) & set(c.members)) >= 2), None)
        if same is None:
            merged.append(c.model_copy())
        else:
            same.members = sorted(set(same.members) | set(c.members))
    return merged


def _evidence_text(pair: PairResult, labels: dict[str, str]) -> str:
    lines = []
    for e in pair.evidence:
        where = f" (question {labels.get(e.question_id, '?')})" if e.question_id else ""
        if e.code == "shared_passage":
            lines.append(f"- identical passages{where}: " + " / ".join(f"“{p}”" for p in e.detail.get("passages", [])))
        elif e.code == "same_wrong_answers":
            lines.append("- the same wrong answers: " + ", ".join(
                f"question {labels.get(x['question_id'], '?')} → {x['value']} (chosen by {x['class_count']} students)"
                for x in e.detail.get("questions", [])))
        elif e.code in ("shared_mistake", "shared_detail"):
            sizes = e.detail.get("sizes", [])
            items = [f"{label} (in {sizes[i]} papers of the class)" if i < len(sizes) else label
                     for i, label in enumerate(e.detail.get("labels", []))]
            lines.append(f"- the same {'mistake' if e.code == 'shared_mistake' else 'distinctive detail'}{where}: " + "; ".join(items))
        else:
            lines.append(f"- {e.code.replace('_', ' ')}: {e.detail}")
    return "\n".join(lines) or "- nothing specific"


def _answers_text(a: Assessment, pa: Paper, pb: Paper) -> str:
    parts = []
    for q in a.rubric.questions:
        ra, rb = pa.result(q.id), pb.result(q.id)
        if ra is None and rb is None:
            continue
        def show(r):
            if r is None or (not r.answer and r.final is None):
                return "(no answer)"
            return (r.answer or r.final or "")[:1200]
        parts.append(f"Question {q.label}: {q.prompt[:300]}\nPaper A: {show(ra)}\nPaper B: {show(rb)}")
    return "\n\n".join(parts)


def _locate(paper: Paper, quote: str, prefer: str | None) -> tuple[str | None, str | None]:
    """(question id, the paper's own words) where the paper says what the model quoted."""
    for r in sorted(paper.results, key=lambda r: r.question_id != prefer):
        words = find_quote(quote, r.answer) if r.answer else None
        if words:
            return r.question_id, words
    return None, None


def shared_items(found: list[_Shared], a: Assessment, pa: Paper, pb: Paper, counts: Counter) -> list[SharedItem]:
    """What the model says both papers share, kept only where both papers really say it (a model can misquote),
    and marked rare when no other paper of the class has what the two quotes have in common."""
    by_label = {re.sub(r"\s+", "", q.label.casefold()): q.id for q in a.rubric.questions}
    out: list[SharedItem] = []
    for item in found[:8]:
        if not item.what.strip():
            continue
        prefer = by_label.get(re.sub(r"\s+", "", item.question.casefold()))
        qa, words_a = _locate(pa, item.a, prefer)
        qb, words_b = _locate(pb, item.b, qa or prefer)
        if not (words_a and words_b) or any((x.a, x.b) == (words_a, words_b) for x in out):
            continue
        out.append(SharedItem(question_id=qa, what=item.what.strip()[:160], a=words_a[:400], b=words_b[:400],
                              rare=shared_rarely(words_a, words_b, counts, RARE_QUOTE_PAPERS)))
    return out


def verdict_of(text: str) -> str:
    """The model's verdict in its canonical form ("Likely copied", "likely-copied", "possibly copied" …)."""
    t = re.sub(r"[^a-z]", "", text.casefold())
    order = (("unlikely", "independent"), ("notcopied", "independent"), ("indep", "independent"), ("possib", "possibly"),
             ("likely", "likely_copied"))
    return next((v for key, v in order if key in t), "")


async def _check_pairs(llm: LLM, call: Call, a: Assessment, papers: dict[str, Paper], pairs: list[PairResult],
                       cohort: list[CohortPaper]) -> list[PairResult]:
    labels = {q.id: q.label for q in a.rubric.questions}
    language = language_name(a.language)
    # Only pairs whose answers resemble each other (the model cannot judge file metadata); the strongest text
    # evidence first, so that pairs sharing one common detail never crowd out a verbatim passage.
    limit = max(MAX_PAIR_CHECKS, len(papers) // 3)
    candidates = sorted((p for p in pairs if p.score >= PAIR_CHECK_FROM and any(e.code in CONTENT for e in p.evidence)),
                        key=lambda p: (not corroborated(p.evidence), -p.score))[:limit]
    prompts = [PAIR_PROMPT.format(title=a.title, evidence=_evidence_text(p, labels),
                                  answers=_answers_text(a, papers[p.a], papers[p.b]), language=language) for p in candidates]
    verdicts = await asyncio.gather(*(call(_ask, llm, pr, _Verdict) for pr in prompts), return_exceptions=True)
    counts = gram_counts(cohort) if candidates else Counter()
    checked = {}
    for pair, v in zip(candidates, verdicts):
        if isinstance(v, BaseException):
            log.warning("pair check failed for %s/%s: %s", pair.a, pair.b, v)
            continue
        found = shared_items(v.shared, a, papers[pair.a], papers[pair.b], counts)
        checked[(pair.a, pair.b)] = apply_verdict(pair, verdict_of(v.verdict), v.explanation, found)
    out = [checked.get((p.a, p.b), p) for p in pairs]
    return sorted(out, key=lambda p: -p.score)


async def _insights(llm: LLM, call: Call, a: Assessment, clusters: list[Cluster]) -> _Insights | None:
    stats = compute_stats(a)
    if not stats.graded:
        return None
    labels = {q.id: q for q in a.rubric.questions}
    qlines = []
    for qs in stats.questions:
        q = labels[qs.question_id]
        pct = f"{round((qs.mean_pct or 0) * 100)}%"
        correct = f", correct {round((qs.correct_rate or 0) * 100)}%" if qs.correct_rate is not None else ""
        qlines.append(f"- id {q.id} · {q.label} ({q.type}, {q.points:g} pts): {q.prompt[:160]} → average {pct}{correct}")
    clines = [f"- question {labels[c.question_id].label}: {c.label} ({len(c.members)})"
              for c in clusters if c.kind == "mistake" and c.question_id in labels]
    prompt = INSIGHTS_PROMPT.format(title=a.title, course=f" — {a.course}" if a.course else "", n=stats.graded,
                                    mean=stats.mean, scale=a.scale, median=stats.median,
                                    pass_rate=f"{round((stats.pass_rate or 0) * 100)}%", questions="\n".join(qlines),
                                    clusters="\n".join(clines) or "- none recorded", language=language_name(a.language))
    try:
        return await call(_ask, llm, prompt, _Insights)
    except Exception as exc:  # noqa: BLE001 - insights are a bonus; the analysis stands without them
        log.warning("class insights failed: %s", exc)
        return None


async def run_class_analysis(store: AssessmentStore, aid: str, llm: LLM, call: Call) -> None:
    a = store.get(aid)
    papers = [p for p in store.papers(aid) if p.status == "graded"]
    if len(papers) < 2:
        def small(x: Assessment) -> None:
            x.analysis = Analysis(status="done", computed_at=datetime.now(timezone.utc), covered=[p.id for p in papers])
        await store.mutate(aid, small)
        await store.refresh_rows(aid)
        return

    def running(x: Assessment) -> None:
        x.analysis.status, x.analysis.error, x.analysis.stale = "running", None, False
    await store.mutate(aid, running)
    try:
        exam_text = store.exam_text(aid)
        questions = a.rubric.questions
        clusters = await _clusters(llm, call, a, papers)
        cohort = await asyncio.to_thread(lambda: [cohort_paper(store, aid, p, questions, exam_text) for p in papers])
        clusters = clusters + example_clusters(cohort, questions, clusters, exam_text)
        pairs = await asyncio.to_thread(pair_results, cohort, questions, clusters, exam_text)
        pairs = await _check_pairs(llm, call, a, {p.id: p for p in papers}, pairs, cohort)
        outliers = class_outliers(cohort, questions)
        estimates = [p.ai.likelihood for p in papers if p.ai is not None and p.ai.words >= 60]
        class_likelihood = statistics.median(estimates) if len(estimates) >= 4 else None
        for p in papers:
            if p.ai is None:
                continue
            updated = with_class_signal(p.ai, outliers.get(p.id, []), class_likelihood)
            if updated != p.ai:
                await store.mutate_paper(aid, p.id, lambda x, u=updated: setattr(x, "ai", u))
        current = store.get(aid)
        insights = await _insights(llm, call, current, clusters)
    except Exception as exc:  # noqa: BLE001 - shown as "Re-run analysis"; previous results stay
        log.exception("class analysis failed for %s", aid)
        message = str(exc)[:500]

        def failed(x: Assessment) -> None:
            x.analysis.status, x.analysis.error = "failed", message
        await store.mutate(aid, failed)
        return

    def done(x: Assessment) -> None:
        known = {r.id for r in x.papers}
        x.analysis.status = "done"
        x.analysis.computed_at = datetime.now(timezone.utc)
        x.analysis.covered = [p.id for p in papers if p.id in known]
        x.analysis.pairs = [p for p in pairs if p.score >= KEEP_PAIRS_FROM and p.a in known and p.b in known][:MAX_PAIRS]
        x.analysis.clusters = [c for c in clusters if all(m in known for m in c.members)]
        if insights is not None:
            x.analysis.insights = insights.insights.strip()[:3000]
            x.analysis.recommendations = [r.strip()[:400] for r in insights.recommendations if r.strip()][:6]
            x.analysis.question_insights = {k: v.strip()[:400] for k, v in insights.questions.items()
                                            if any(q.id == k for q in x.rubric.questions)}
    await store.mutate(aid, done)
    await store.refresh_rows(aid)
