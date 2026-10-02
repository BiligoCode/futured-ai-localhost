"""The AI-likeness score (design §8): a noisy-OR of explained signals, damped on short text, never a verdict.

Only the student's own writing is measured: on scans the transcribed answers, on typed pages the visible text minus
lines copied from the exam paper. Punctuation and invisible-character signals apply to typed text only: a pen does
not distinguish an em dash from a hyphen."""
import math
import re
import statistics

from app.assess.answers import normalize_text
from app.assess.lexicon import (AI_WORDS_EL, AI_WORDS_EN, CHAT_ARTIFACTS, CITATION_ARTIFACTS, EM_DASH, FORMULAIC,
                                MARKDOWN, invisible_counts)
from app.assess.models import AiAnalysis, Paper, Signal

MIN_WORDS = 60
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
_SENTENCE_END = re.compile(r"(?<=[.!?;·])\s+|\n{2,}")
STRONG = {"chat_artifact", "citation_artifact", "invisible_chars", "markdown_artifact"}


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _damp(n: int, hits: int, full_words: int = 200, full_hits: int = 8, min_hits: int = 2) -> float:
    """How much a rate can be trusted: enough words, or enough hits (a dense short text is evidence too). A single
    occurrence is never evidence — one "crucial" or one dash says nothing about who wrote a text."""
    if hits < min_hits:
        return 0.0
    return min(1.0, max(n / full_words, hits / full_hits))


def _lex(text: str) -> str:
    return normalize_text(text).replace("’", "'").replace("‘", "'")


def _ngrams(tokens: list[str], n: int = 4) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def strip_exam_lines(text: str, exam_text: str) -> str:
    """Drop lines the student copied from the exam paper (question statements pasted into a typed answer)."""
    if not exam_text.strip():
        return text
    exam = _ngrams(words(normalize_text(exam_text)))
    kept = []
    for line in text.splitlines():
        grams = _ngrams(words(normalize_text(line)))
        if len(grams) >= 3 and len(grams & exam) / len(grams) >= 0.6:
            continue
        kept.append(line)
    return "\n".join(kept)


def student_text(paper: Paper, exam_text: str = "") -> tuple[str, bool]:
    """(the student's own writing, whether it is mostly typed)."""
    typed_parts, written_parts = [], []
    for page in paper.reading:
        if page.text:
            typed_parts.append(page.text)
        written_parts.extend(b.text for b in page.blocks if b.text.strip())
    typed = strip_exam_lines("\n".join(typed_parts), exam_text)
    written = re.sub(r"~~.*?~~", " ", "\n".join(written_parts), flags=re.DOTALL)
    written = re.sub(r"\[figure:[^\]]*\]|\((?:circled|ticked|underlined): ?[^)]*\)", " ", written)
    return ("\n".join(p for p in (typed, written) if p.strip()),
            len(words(typed)) > len(words(written)))


def _sentences(text: str) -> list[int]:
    lengths = []
    for s in _SENTENCE_END.split(text):
        n = len(words(s))
        if n >= 3:
            lengths.append(n)
    return lengths


def ai_analysis(text: str, typed: bool, likelihood: int = 0, reasons: list[str] | None = None) -> AiAnalysis:
    tokens = words(text)
    n = len(tokens)
    lex = _lex(text)
    signals: list[Signal] = []

    def add(code: str, strength: float, **detail) -> None:
        if strength >= 0.01:
            signals.append(Signal(code=code, strength=round(min(strength, 0.97), 3), detail=detail))

    if chat := sorted({m.group(0) for m in CHAT_ARTIFACTS.finditer(lex)}):
        add("chat_artifact", 0.9, samples=chat[:5])
    if cites := sorted({m.group(0) for m in CITATION_ARTIFACTS.finditer(text)}):
        add("citation_artifact", 0.95, samples=cites[:5])
    if typed:
        md = MARKDOWN.findall(text)
        if len(md) >= 2:
            add("markdown_artifact", 0.5, count=len(md), samples=sorted(set(m.strip() for m in md))[:4])
        counts = invisible_counts(text)
        hidden = {k: v for k, v in counts.items() if k != "NARROW NO-BREAK SPACE"}
        if hidden:
            add("invisible_chars", 0.6, counts=counts)
        elif counts.get("NARROW NO-BREAK SPACE", 0) >= 3:
            add("invisible_chars", 0.45, counts=counts)
    if n:
        hits = [m.group(0) for m in AI_WORDS_EN.finditer(lex)] + [m.group(0) for m in AI_WORDS_EL.finditer(lex)]
        # Distinct words: AI style shows many different such words; one technical term repeated is just the topic.
        distinct = sorted({h[:7] for h in hits})
        rate = len(distinct) / n * 1000
        add("ai_vocabulary", min(0.8, _clamp((rate - 3) / 15) * _damp(n, len(distinct))), rate=round(rate, 1),
            count=len(distinct), samples=[w for w, _ in sorted(((w, hits.count(w)) for w in set(hits)), key=lambda x: -x[1])][:8])
        formulas = [m.group(0) for m in FORMULAIC.finditer(lex)]
        f_rate = len(formulas) / n * 1000
        add("formulaic", min(0.35, _clamp((f_rate - 2) / 12) * _damp(n, len(formulas), full_hits=5)),
            rate=round(f_rate, 1), count=len(formulas),
            samples=sorted(set(formulas))[:6])
        if typed:
            dashes = text.count(EM_DASH)
            d_rate = dashes / n * 1000
            add("em_dash", min(0.6, _clamp((d_rate - 1.5) / 8) * _damp(n, dashes, full_hits=6, min_hits=3)), rate=round(d_rate, 1),
                count=dashes)
        lengths = _sentences(text)
        if len(lengths) >= 10:
            cv = statistics.pstdev(lengths) / statistics.mean(lengths)
            if cv < 0.3:
                add("uniform_sentences", 0.1, cv=round(cv, 2), sentences=len(lengths))
    if likelihood > 0 and n:
        # On its own the model's estimate is weak evidence: it rates most polished text as AI-like, human or not.
        # The class analysis replaces this with the estimate relative to the rest of the class (lara_vs_class).
        add("lara_reading", 0.2 * (likelihood / 100) ** 2 * min(1.0, n / 120), likelihood=likelihood)
    return finish(AiAnalysis(words=n, signals=signals, likelihood=likelihood,
                             note=" ".join(r.strip() for r in (reasons or []) if r.strip())[:1000]))


def finish(ai: AiAnalysis) -> AiAnalysis:
    """Combine the signals (noisy-OR) and set the level."""
    ai.signals = sorted(ai.signals, key=lambda s: -s.strength)
    score = 100 * (1 - math.prod(1 - s.strength for s in ai.signals))
    if ai.words < MIN_WORDS and not any(s.code in STRONG for s in ai.signals):
        ai.score, ai.level = min(25, round(score)), "insufficient"
        return ai
    ai.score = round(score)
    ai.level = "low" if ai.score < 30 else "some" if ai.score < 60 else "strong"
    return ai


def with_class_signal(ai: AiAnalysis, outliers: list[dict], class_likelihood: float | None = None) -> AiAnalysis:
    """Add (or refresh) the class-relative signals: answers far longer and more sophisticated than everyone else's to
    the same question, and the model's AI estimate compared with the class median (only a paper that stands out from
    its own class counts — the model's absolute estimate is high for most polished text)."""
    ai = ai.model_copy(deep=True)
    ai.signals = [s for s in ai.signals if s.code not in ("over_elaborate", "lara_vs_class")]
    if outliers:
        ai.signals.append(Signal(code="over_elaborate", strength=round(min(0.4, 0.15 * len(outliers)), 3),
                                 detail={"questions": outliers[:5]}))
    if class_likelihood is not None:
        ai.signals = [s for s in ai.signals if s.code != "lara_reading"]
        above = ai.likelihood - max(class_likelihood, 25)
        strength = 0.5 * _clamp(above / 60) * min(1.0, ai.words / 120)
        if strength >= 0.01:
            ai.signals.append(Signal(code="lara_vs_class", strength=round(strength, 3),
                                     detail={"likelihood": ai.likelihood, "class_median": round(class_likelihood)}))
    return finish(ai)


def sophistication(text: str) -> float:
    """Mean word length plus the share of long words (≥ 9 letters) — a rough register measure, comparable within one
    question of one class."""
    tokens = words(text)
    if not tokens:
        return 0.0
    return statistics.mean(len(t) for t in tokens) + 10 * sum(1 for t in tokens if len(t) >= 9) / len(tokens)
