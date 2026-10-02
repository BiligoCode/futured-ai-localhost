"""Copying evidence between two papers, always judged against the whole class (design §7).

Every signal is a strength in [0, 1]; a pair's score is their noisy-OR. Material that many students share — the
question's own words, the lecture's standard phrasing, a common misconception, the printed exam template — is
removed before anything is compared, because it is not evidence of copying."""
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from itertools import combinations

import numpy as np

from app.assess.answers import compact, normalize_text, parse_choices, parse_numbers, parse_true_false
from app.assess.models import Cluster, Evidence, PairResult, Question, SharedItem

COMMON_SHARE = 0.2        # an n-gram (or skipped question, or cluster) shared by more of the class is common
MIN_STYLE_WORDS = 150
PAGE_CONTENT = 0.004      # mean residual ink below this: the student wrote (almost) nothing on that page
PRIOR_WEIGHT = 2.0        # how many answers the prior below is worth when estimating a question's wrong answers
FREE_WRONG = 0.1          # prior chance that two wrong free answers (a number, a word) are the same
CLUSTER_CAP = {"detail": 0.4, "mistake": 0.3}  # one shared detail or mistake alone is at most "worth a look"
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass
class CohortPaper:
    id: str
    name: str = ""
    answers: dict[str, str] = field(default_factory=dict)            # question id → the student's answer text
    finals: dict[str, tuple[str, bool]] = field(default_factory=dict)  # definitive question → (value, correct)
    skipped: set[str] = field(default_factory=set)
    style_text: str = ""
    pages: list[tuple[int, str, np.ndarray | None]] = field(default_factory=list)  # (n, dhash, ink map)
    kind: str = "scanned"
    split: bool = False
    sha256: str = ""
    file_id: str | None = None
    document_id: str | None = None
    author: str = ""
    created: datetime | None = None


def final_value(question: Question, final: str | None) -> str | None:
    """A definitive answer in one comparable form, or None when there is nothing to compare."""
    if final is None or not normalize_text(final):
        return None
    if question.type == "true_false":
        v = parse_true_false(final)
        return None if v is None else str(v).lower()
    if question.type == "multiple_choice":
        v = parse_choices(final, question.options)
        return None if v is None else ",".join(str(i) for i in sorted(v))
    if question.type == "numeric":
        nums = parse_numbers(final)
        return f"{nums[0]:.6g}" if nums else None
    return compact(final) or None


def tokens(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    """(normalised tokens, their character spans in the text with crossed-out parts blanked), index by index."""
    clean = re.sub(r"~~.*?~~", lambda m: " " * len(m.group(0)), text or "", flags=re.DOTALL)
    found = list(_WORD.finditer(clean))
    return [normalize_text(m.group(0)) for m in found], [m.span() for m in found]


def _grams(toks: list[str], k: int) -> set[tuple[str, ...]]:
    return {tuple(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _wrong_prior(q: Question | None) -> float:
    """Before seeing the class: how likely two wrong answers to the question are the same one. Certain for
    true/false (there is one wrong answer), one in (options − 1) for a choice, small for a free answer."""
    if q is None or q.type in ("numeric", "short"):
        return FREE_WRONG
    if q.type == "true_false":
        return 1.0
    k = max(2, len(q.options) or 4)
    key = parse_choices(q.answer or "", q.options) or set()
    return 1 / ((2 ** k - 2) if len(key) > 1 else (k - 1))


def _tail(probs: list[float], matched: list[bool], unit: float = 0.1) -> float:
    """P(S ≥ observed) for S = Σ −ln p over the questions that match, each matching independently with its own
    probability p — computed exactly over weights rounded to `unit`."""
    weights = [max(1, int(-math.log(max(p, 1e-12)) / unit)) for p in probs]
    target = sum(w for w, m in zip(weights, matched) if m)
    if target == 0:
        return 1.0
    dist = np.zeros(target + 1)  # the last cell collects everything at or above the target
    dist[0] = 1.0
    for p, w in zip(probs, weights):
        moved = np.zeros_like(dist)
        if w >= target:
            moved[target] = dist.sum()
        else:
            moved[w:target] = dist[:target - w]
            moved[target] = dist[target - w:].sum()
        dist = (1 - p) * dist + p * moved
    return float(min(1.0, dist[target]))


class _WrongAnswers:
    """Identical wrong answers, judged against chance. Two students being wrong on the same question is explained
    by how hard the question is and how strong each of them is; the evidence is *which* wrong answer they both
    gave — rare wrong answers, matched on more questions than chance allows. For "b copied a", each of a's wrong
    answers that b also answered matches by chance with P(b is wrong there) × P(that wrong answer | wrong), both
    estimated from the rest of the class; the pair's p-value is corrected for the number of pairs in the class."""

    def __init__(self, papers: list[CohortPaper], questions: list[Question]):
        self.questions = {q.id: q for q in questions}
        self.values: dict[str, Counter] = defaultdict(Counter)
        self.answered: Counter = Counter()
        self.wrong: Counter = Counter()
        self.rate: dict[str, float] = {}
        total = wrong = 0
        for p in papers:
            w = sum(1 for _, ok in p.finals.values() if not ok)
            self.rate[p.id] = (w + 1) / (len(p.finals) + 2)
            total, wrong = total + len(p.finals), wrong + w
            for qid, (value, ok) in p.finals.items():
                self.answered[qid] += 1
                if not ok:
                    self.wrong[qid] += 1
                    self.values[qid][value] += 1
        self.overall = (wrong + 1) / (total + 2)
        self.pairs = max(1, len(papers) * (len(papers) - 1) // 2)

    def _chances(self, src: CohortPaper, dst: CohortPaper) -> tuple[list[float], list[bool]]:
        probs, matched = [], []
        for qid, (value, ok) in src.finals.items():
            if ok or qid not in dst.finals:
                continue
            other_value, other_ok = dst.finals[qid]
            same = not other_ok and other_value == value
            # The rest of the class (without this pair): how often it gets the question wrong, and with what.
            wrong_rest = self.wrong[qid] - 1 - (0 if other_ok else 1)
            q_rate = (wrong_rest + 1) / (self.answered[qid] - 2 + 2)
            p_wrong = 1 / (1 + math.exp(-(_logit(self.rate[dst.id]) + _logit(q_rate) - _logit(self.overall))))
            value_rest = self.values[qid][value] - 1 - (1 if same else 0)
            share = (value_rest + PRIOR_WEIGHT * _wrong_prior(self.questions.get(qid))) / (wrong_rest + PRIOR_WEIGHT)
            probs.append(min(0.99, p_wrong * min(1.0, share)))
            matched.append(same)
        return probs, matched

    def evidence(self, a: CohortPaper, b: CohortPaper) -> Evidence | None:
        shared = [(qid, v) for qid, (v, ok) in a.finals.items() if not ok and b.finals.get(qid) == (v, False)]
        if not shared:
            return None
        p = min(_tail(*self._chances(a, b)), _tail(*self._chances(b, a)))
        adjusted = min(1.0, 2 * p * self.pairs)  # either could have copied; any pair of the class could show it
        strength = min(0.85, 0.25 * -math.log10(adjusted)) if adjusted < 1 else 0.0
        if strength < 0.05:
            return None
        shared.sort(key=lambda x: self.values[x[0]][x[1]])
        return Evidence(code="same_wrong_answers", strength=round(strength, 3),
                        detail={"count": len(shared), "p": round(adjusted, 4),
                                "questions": [{"question_id": qid, "value": v, "class_count": self.values[qid][v]}
                                              for qid, v in shared][:12]})


def gram_counts(papers: list[CohortPaper]) -> Counter:
    """In how many papers of the class each three-word sequence appears (any answer)."""
    counts: Counter = Counter()
    for p in papers:
        seen: set[tuple[str, ...]] = set()
        for text in p.answers.values():
            toks = tokens(text)[0]
            seen.update(zip(toks, toks[1:], toks[2:]))
        counts.update(seen)
    return counts


def shared_rarely(words_a: str, words_b: str, counts: Counter, limit: int = 2) -> bool:
    """Whether what two quotes have in common is theirs alone: the three-word sequences of their common runs (the
    whole phrase when it is quoted verbatim) occur in at most `limit` papers of the class, mostly. A paraphrase with
    no common run cannot be shown to be rare, and one of what everyone writes is not."""
    ta, tb = tokens(words_a)[0], tokens(words_b)[0]
    runs = [m for m in SequenceMatcher(None, ta, tb, autojunk=False).get_matching_blocks() if m.size >= 3]
    grams = [tuple(ta[m.a + i:m.a + i + 3]) for m in runs for i in range(m.size - 2)]
    return bool(grams) and sum(counts[g] <= limit for g in grams) >= 0.5 * len(grams)


def _number_grams(text: str) -> set[tuple[str, ...]]:
    """Three numbers in a row ("[9, 4, 7, 1]" → (9, 4, 7), (4, 7, 1)) — an example's values; counting (1, 2, 3)
    and repeats are not examples."""
    out: set[tuple[str, ...]] = set()
    run: list[str] = []
    for tok in tokens(text)[0] + [""]:
        if tok.isdigit():
            run.append(tok)
            continue
        for i in range(len(run) - 2):
            g = tuple(run[i:i + 3])
            steps = {int(g[1]) - int(g[0]), int(g[2]) - int(g[1])}
            if steps not in ({1}, {-1}, {0}):
                out.add(g)
        run = []
    return out


def example_clusters(papers: list[CohortPaper], questions: list[Question], clusters: list[Cluster],
                     exam_text: str = "") -> list[Cluster]:
    """The same example values in the answers of few papers of the class — an objective "same distinctive detail",
    added where the model's grouping (§6.6) did not already group those papers on that question."""
    limit = max(2, COMMON_SHARE * len(papers) + 1)
    printed = _number_grams(exam_text)
    out: list[Cluster] = []
    for q in questions:
        if q.type not in ("open", "short", "numeric"):
            continue
        skip = printed | _number_grams(" ".join((q.prompt, q.model_answer, q.answer)))
        holders: dict[tuple[str, ...], set[str]] = defaultdict(set)
        for p in papers:
            for g in _number_grams(p.answers.get(q.id, "")) - skip:
                holders[g].add(p.id)
        groups: dict[frozenset[str], set[tuple[str, ...]]] = defaultdict(set)
        for g, members in holders.items():
            if 2 <= len(members) <= limit:
                groups[frozenset(members)].add(g)
        for members, grams in groups.items():
            if any(c.question_id == q.id and c.kind == "detail" and members <= set(c.members) for c in clusters):
                continue
            first = next(p for p in papers if p.id == min(members))
            toks = tokens(first.answers.get(q.id, ""))[0]
            hit = [any(tuple(toks[j:j + 3]) in grams for j in range(max(0, i - 2), i + 1)) for i in range(len(toks))]
            best, start = (0, 0), None
            for i, h in enumerate(hit + [False]):
                if h and start is None:
                    start = i
                elif not h and start is not None:
                    best, start = max(best, (i - start, start)), None
            label = "[" + ", ".join(toks[best[1]:best[1] + best[0]]) + "]"
            out.append(Cluster(question_id=q.id, kind="detail", label=label, members=sorted(members)))
    return out


def _cluster_weight(kind: str, size: int, n: int) -> float:
    """One mistake or detail the pair shares with few others: the rarer in the class, the stronger — up to the
    kind's cap, so that one coincidence alone stays "worth a look". Times 2/size: when a group of m papers shares
    it, about 2 of every m pairs in the group are a direct copy (m − 1 links among m(m − 1)/2 pairs)."""
    if size < 2 or n < 3:
        return 0.0
    rarity = max(0.0, min(1.0, (math.log((n - 1) / (size - 1)) - math.log(2)) / 2))
    return CLUSTER_CAP[kind] * rarity * 2 / size


def find_quote(quote: str, text: str) -> str | None:
    """The text's own words for a quoted phrase (give or take a word or a spelling), or None when the text does
    not contain it — a model's citation, checked against the paper."""
    q, _ = tokens(quote)
    t, spans = tokens(text)
    if len(q) < 3 or not t:
        return None
    best, where = 0, (0, 0)
    for start in range(max(1, len(t) - len(q) + 1)):
        blocks = [m for m in SequenceMatcher(None, q, t[start:start + len(q) + 2], autojunk=False).get_matching_blocks() if m.size]
        hit = sum(m.size for m in blocks)
        if hit > best:
            best, where = hit, (start + blocks[0].b, start + blocks[-1].b + blocks[-1].size - 1)
            if best == len(q):
                break
    if best < max(3, 0.8 * len(q)):
        return None
    return text[spans[where[0]][0]:spans[where[1]][1]]


def _robust_threshold(values: list[float], z: float) -> float:
    if not values:
        return math.inf
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values) * 1.4826
    return med + z * mad


def _strength(x: float) -> float:
    return max(0.0, min(1.0, x))


class _Passages:
    """Shared rare passages per question."""

    def __init__(self, papers: list[CohortPaper], questions: list[Question], exam_text: str):
        self.n = len(papers)
        self.toks: dict[tuple[str, str], tuple[list[str], list[tuple[int, int]]]] = {}
        self.texts: dict[tuple[str, str], str] = {}
        self.grams: dict[tuple[str, str, int], set] = {}
        self.df: dict[tuple[str, int], Counter] = {}
        self.covered: dict[tuple[str, str, int], list[bool]] = {}
        text_questions = [q for q in questions if q.type in ("open", "short", "numeric")]
        self.questions = [q.id for q in text_questions]
        exam_toks = tokens(exam_text)[0]
        for q in text_questions:
            excluded = {k: _grams(exam_toks, k) | _grams(tokens(q.prompt + " " + q.model_answer + " " + q.answer)[0], k)
                        for k in (4, 5)}
            df: dict[int, Counter] = {4: Counter(), 5: Counter()}
            for p in papers:
                self.texts[(p.id, q.id)] = p.answers.get(q.id, "")
                t = tokens(self.texts[(p.id, q.id)])
                self.toks[(p.id, q.id)] = t
                for k in (4, 5):
                    g = _grams(t[0], k) - excluded[k]
                    self.grams[(p.id, q.id, k)] = g
                    df[k].update(g)
            limit = max(3, 0.25 * self.n)
            for k in (4, 5):
                self.df[(q.id, k)] = df[k]
            for p in papers:
                toks = self.toks[(p.id, q.id)][0]
                for k in (4, 5):
                    key = (p.id, q.id, k)
                    self.grams[key] = {g for g in self.grams[key] if df[k][g] <= limit}
                    # Words inside common or excluded phrases: trimmed from the ends of a shared passage.
                    covered = [False] * len(toks)
                    for i in range(len(toks) - k + 1):
                        g = tuple(toks[i:i + k])
                        if g in excluded[k] or df[k][g] > limit:
                            for j in range(i, i + k):
                                covered[j] = True
                    self.covered[key] = covered

    def evidence(self, a: str, b: str) -> list[Evidence]:
        out = []
        for qid in self.questions:
            ta, oa = self.toks[(a, qid)]
            tb = self.toks[(b, qid)][0]
            if len(ta) < 4 or len(tb) < 4:
                continue
            k = 4 if len(ta) < 40 and len(tb) < 40 else 5
            shared = self.grams[(a, qid, k)] & self.grams[(b, qid, k)]
            if not shared:
                continue
            starts = [i for i in range(len(ta) - k + 1) if tuple(ta[i:i + k]) in shared]
            runs: list[tuple[int, int]] = []
            for i in starts:
                if runs and i <= runs[-1][1] + 1:
                    runs[-1] = (runs[-1][0], i)
                else:
                    runs.append((i, i))
            df = self.df[(qid, k)]
            covered = self.covered[(a, qid, k)]
            spans = []
            for s, e in ((s, e + k) for s, e in runs):
                while s < e and covered[s]:
                    s += 1
                while e > s and covered[e - 1]:
                    e -= 1
                if e - s >= k:
                    spans.append((s, e))
            if not spans:
                continue
            longest = max(e - s for s, e in spans)
            if longest < 6:
                continue
            weight = 0.0
            for s, e in spans:
                # A passage three or four students share is still evidence, a little weaker than one only two share.
                rarity = statistics.mean(1 / math.sqrt(max(1, df[tuple(ta[i:i + k])] - 1)) for i in range(s, e - k + 1))
                weight += max(0, (e - s) - 5) * rarity
            text = self.texts[(a, qid)]
            passages = [" ".join(text[oa[s][0]:oa[e - 1][1]].split())[:300] for s, e in sorted(spans, key=lambda x: x[0] - x[1])[:3]]
            out.append(Evidence(code="shared_passage", strength=0.0, question_id=qid,
                                detail={"words": sum(e - s for s, e in spans), "longest": longest,
                                        "weight": round(weight, 2), "passages": passages}))
        return out


def _ink_vectors(papers: list[CohortPaper]) -> dict[tuple[str, int], tuple[np.ndarray, str]]:
    """Each page's ink minus the class median for that page number (the printed template), unit-normalised."""
    by_n: dict[int, list[tuple[str, np.ndarray, str]]] = defaultdict(list)
    for p in papers:
        for n, dh, ink in p.pages:
            if ink is not None:
                by_n[n].append((p.id, ink.astype(np.float32), dh))
    out = {}
    for n, items in by_n.items():
        shapes = {i[1].shape for i in items}
        if len(shapes) != 1:
            continue
        median = np.median(np.stack([i[1] for i in items]), axis=0) if len(items) >= 4 else np.zeros(next(iter(shapes)), np.float32)
        for pid, ink, dh in items:
            residual = np.clip(ink - median, 0, None).ravel()
            if residual.mean() < PAGE_CONTENT:
                continue
            centred = residual - residual.mean()
            norm = float(np.linalg.norm(centred))
            if norm > 0:
                out[(pid, n)] = (centred / norm, dh)
    return out


def _hamming(a: str, b: str) -> int:
    try:
        return (int(a, 16) ^ int(b, 16)).bit_count()
    except ValueError:
        return 64


def _style_matrix(papers: list[CohortPaper]) -> tuple[list[str], np.ndarray | None]:
    eligible = [p for p in papers if len(tokens(p.style_text)[0]) >= MIN_STYLE_WORDS]
    if len(eligible) < 3:
        return [], None
    grams = []
    for p in eligible:
        text = " ".join(tokens(p.style_text)[0])
        grams.append(Counter(text[i:i + 3] for i in range(len(text) - 2)))
    df = Counter(g for c in grams for g in c)
    vocab = [g for g, _ in df.most_common(3000)]
    index = {g: i for i, g in enumerate(vocab)}
    m = np.zeros((len(eligible), len(vocab)), np.float32)
    for row, c in enumerate(grams):
        for g, v in c.items():
            if g in index:
                m[row, index[g]] = v
    m = np.log1p(m)
    m -= m.mean(axis=0, keepdims=True)  # what everyone writes says nothing about who wrote it
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    m = m / np.where(norms == 0, 1, norms)
    return [p.id for p in eligible], m @ m.T


def _generic_author(author: str) -> bool:
    from app.assess.forensics import GENERIC_AUTHORS
    return normalize_text(author) in {normalize_text(g) for g in GENERIC_AUTHORS}


def _names_overlap(a: str, b: str) -> bool:
    x = set(re.findall(r"\w{3,}", normalize_text(a)))
    y = set(re.findall(r"\w{3,}", normalize_text(b)))
    return bool(x and y and (x & y or any(i[:4] == j[:4] for i in x for j in y)))


def pair_results(papers: list[CohortPaper], questions: list[Question], clusters: list[Cluster],
                 exam_text: str = "") -> list[PairResult]:
    """Every pair with any evidence, scored (before the model's side-by-side check)."""
    n = len(papers)
    if n < 2:
        return []
    passages = _Passages(papers, questions, exam_text)
    wrong_answers = _WrongAnswers(papers, questions)
    skip_counts: Counter = Counter()
    for p in papers:
        skip_counts.update(p.skipped)

    members: dict[str, list[Cluster]] = defaultdict(list)
    for c in clusters:
        if 2 <= len(c.members) <= max(2, COMMON_SHARE * n + 1):
            for m in c.members:
                members[m].append(c)

    ink = _ink_vectors(papers)
    style_ids, style = _style_matrix(papers)
    style_pos = {pid: i for i, pid in enumerate(style_ids)}
    style_values = [float(style[i, j]) for i, j in combinations(range(len(style_ids)), 2)] if style is not None else []
    style_cut = max(_robust_threshold(style_values, 3.5), 0.35) if style_values else math.inf

    id_counts = Counter(x for p in papers if not p.split for x in {p.file_id, p.document_id} if x)
    created = [p.created for p in papers if p.created and not p.split]
    near_count = {p.id: sum(1 for c in created if abs((c - p.created).total_seconds()) <= 120) - 1
                  for p in papers if p.created and not p.split}
    author_counts = Counter(normalize_text(p.author) for p in papers if p.author and not _generic_author(p.author))
    informative = max(2, 0.3 * n)

    raw: list[tuple[CohortPaper, CohortPaper, list[Evidence]]] = []
    layout_values: list[float] = []
    for a, b in combinations(papers, 2):
        ev: list[Evidence] = []

        for e in passages.evidence(a.id, b.id):
            # Per question 1 − exp(−w/20): their noisy-OR is 1 − exp(−Σw/20), the design's passage strength.
            e.strength = round(1 - math.exp(-e.detail["weight"] / 20), 3)
            ev.append(e)

        wrong = wrong_answers.evidence(a, b)
        if wrong is not None:
            ev.append(wrong)

        for kind, code in (("mistake", "shared_mistake"), ("detail", "shared_detail")):
            shared = [c for c in members.get(a.id, []) if c.kind == kind and b.id in c.members]
            if shared:
                # The same unusual example or wording is stronger evidence than the same mistake (the caps).
                strength = 1 - math.prod(1 - _cluster_weight(kind, len(c.members), n) for c in shared)
                if strength > 0:
                    ev.append(Evidence(code=code, strength=round(strength, 3), question_id=shared[0].question_id,
                                       detail={"labels": [c.label for c in shared][:6], "sizes": [len(c.members) for c in shared][:6],
                                               "questions": sorted({c.question_id for c in shared})}))

        rare_skips = [q for q in a.skipped & b.skipped if skip_counts[q] <= max(2, COMMON_SHARE * n)]
        if rare_skips:
            ev.append(Evidence(code="same_skipped", strength=round(min(0.25, 0.08 * len(rare_skips)), 3),
                               detail={"questions": sorted(rare_skips)}))

        best_r, best_page, same_image = -1.0, None, False
        for n_page, dh, _ in a.pages:
            va, vb = ink.get((a.id, n_page)), ink.get((b.id, n_page))
            if va is None or vb is None:
                continue
            r = float(va[0] @ vb[0])
            layout_values.append(r)
            if r > best_r:
                best_r, best_page = r, n_page
            if r >= 0.95 and _hamming(va[1], vb[1]) <= 6:
                same_image = True
        if same_image:
            ev.append(Evidence(code="same_page_image", strength=0.95, detail={"page": best_page, "r": round(best_r, 3)}))
        elif best_page is not None:
            ev.append(Evidence(code="page_layout", strength=0.0, detail={"page": best_page, "r": round(best_r, 3)}))

        if a.sha256 and a.sha256 == b.sha256:
            ev.append(Evidence(code="same_file", strength=1.0, detail={}))
        docs_comparable = not a.split and not b.split and a.kind in ("typed", "mixed") and b.kind in ("typed", "mixed")
        if docs_comparable:
            shared_ids = {x for x in (a.file_id, a.document_id) if x} & {x for x in (b.file_id, b.document_id) if x}
            if any(id_counts[x] <= informative for x in shared_ids) and a.sha256 != b.sha256:
                ev.append(Evidence(code="same_document_id", strength=0.9, detail={}))
            na, nb = normalize_text(a.author), normalize_text(b.author)
            if na and na == nb and not _generic_author(a.author) and author_counts[na] <= min(3, informative):
                ev.append(Evidence(code="same_author", strength=0.5, detail={"author": a.author[:120]}))
            for x, y in ((a, b), (b, a)):
                # x's file says it was written by y (and not by x): y most likely handed over the file.
                if x.author and not _generic_author(x.author) and y.name and _names_overlap(x.author, y.name) \
                        and not _names_overlap(x.author, x.name):
                    ev.append(Evidence(code="author_is_student", strength=0.85,
                                       detail={"author": x.author[:120], "paper": x.id, "student": y.id}))
                    break
            if a.created and b.created and abs((a.created - b.created).total_seconds()) <= 120 and \
                    max(near_count.get(a.id, 0), near_count.get(b.id, 0)) <= max(1, informative - 1):
                ev.append(Evidence(code="close_creation", strength=0.25,
                                   detail={"seconds": int(abs((a.created - b.created).total_seconds()))}))

        if a.id in style_pos and b.id in style_pos:
            sim = float(style[style_pos[a.id], style_pos[b.id]])
            if sim >= style_cut:
                ev.append(Evidence(code="similar_style", strength=round(min(0.3, 0.12 + (sim - style_cut)), 3),
                                   detail={"similarity": round(sim, 3)}))
        raw.append((a, b, ev))

    layout_cut = _robust_threshold(layout_values, 3.5) if len(layout_values) >= 10 else 0.95
    out: list[PairResult] = []
    for a, b, ev in raw:
        kept = []
        for e in ev:
            if e.code == "page_layout":
                r = e.detail["r"]
                if r >= max(0.85, layout_cut):
                    e.strength = 0.7 if r >= 0.92 else 0.3
            if e.strength > 0:
                kept.append(e)
        if not kept:
            continue
        kept.sort(key=lambda e: -e.strength)
        out.append(PairResult(a=min(a.id, b.id), b=max(a.id, b.id), score=combine(kept), evidence=kept))
    return sorted(out, key=lambda p: -p.score)


def combine(evidence: list[Evidence]) -> int:
    return round(100 * (1 - math.prod(1 - min(0.999, e.strength) for e in evidence)))


HARD = {"same_file", "same_document_id", "same_page_image"}
CONTENT = {"shared_passage", "same_wrong_answers", "shared_mistake", "shared_detail", "same_skipped", "page_layout",
           "same_page_image", "similar_style"}
STRONG_FROM = 0.3   # one signal this strong carries "likely" on its own
NOTABLE_FROM = 0.15  # two independent coincidences this strong do too
PAIR_GROUP = 3       # a mistake or detail shared by more papers says little about one pair


def corroborated(evidence: list[Evidence]) -> bool:
    """Objective evidence that can carry "likely": the same file, a long shared passage, identical wrong answers
    beyond chance, nearly the same page — or two independent coincidences (a rare detail *and* a rare mistake,
    passages in two questions…); a mistake or detail counts when at most three papers share it. One shared detail is
    not enough: two students can pick the same example."""
    coincidences = 0
    for e in evidence:
        if e.code in HARD or e.code == "author_is_student":
            return True
        if e.code in ("shared_passage", "same_wrong_answers") and e.strength >= STRONG_FROM:
            return True
        if e.code == "page_layout" and e.strength >= 0.7:
            return True
        if e.code in ("shared_passage", "same_wrong_answers", "page_layout") and e.strength >= NOTABLE_FROM:
            coincidences += 1
        elif e.code in ("shared_mistake", "shared_detail") and e.strength >= NOTABLE_FROM:
            coincidences += sum(1 for size in e.detail.get("sizes", [2]) if size <= PAIR_GROUP)
    return coincidences >= 2


def apply_verdict(pair: PairResult, verdict: str, explanation: str, shared: list[SharedItem] | None = None) -> PairResult:
    """The model's side-by-side reading moves the score only as far as the evidence allows (design §7.4):
    "likely copied" reaches 75 when objective evidence — or at least two rare things the model found in both
    papers, quoted and checked — backs it, and stays "worth a look" (≤ 59) otherwise; "possibly" caps at 59;
    "independent" lowers the score, but strong evidence stays worth a look. Identical files are never moved."""
    pair = pair.model_copy(deep=True)
    pair.verdict = verdict if verdict in ("likely_copied", "possibly", "independent") else ""
    pair.explanation = explanation.strip()[:800]
    pair.shared = list(shared or [])[:6]
    score = combine(pair.evidence)
    hard = any(e.code in HARD for e in pair.evidence)
    strong = corroborated(pair.evidence)
    if pair.verdict == "likely_copied":
        backed = strong or sum(1 for s in pair.shared if s.rare) >= 2
        score = max(score, 75) if backed else max(score, min(59, score + 15))
        pair.evidence.append(Evidence(code="lara_verdict", strength=0.75, detail={"verdict": pair.verdict}))
    elif pair.verdict == "possibly" and not hard:
        score = min(score, 59)
    elif pair.verdict == "independent" and not hard:
        score = min(score, 59) if strong else round(score * 0.6)
    pair.score = min(100, score)
    return pair


def class_outliers(papers: list[CohortPaper], questions: list[Question]) -> dict[str, list[dict]]:
    """Answers far longer *and* far more sophisticated than the rest of the class wrote for the same question."""
    from app.assess.signals import sophistication

    out: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        if q.type not in ("open", "short"):
            continue
        rows = []
        for p in papers:
            text = p.answers.get(q.id, "")
            n_words = len(tokens(text)[0])
            if n_words >= 15:
                rows.append((p.id, math.log1p(n_words), sophistication(text), n_words))
        if len(rows) < 5:
            continue
        lengths = [r[1] for r in rows]
        sophs = [r[2] for r in rows]
        len_cut = _robust_threshold(lengths, 2.5)
        soph_cut = _robust_threshold(sophs, 2.0)
        median_words = statistics.median(r[3] for r in rows)
        for pid, length, soph, n_words in rows:
            if length > len_cut and soph > soph_cut:
                out[pid].append({"question": q.label, "words": n_words, "class_median": round(median_words)})
    return out
