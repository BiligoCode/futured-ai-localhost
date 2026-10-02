import random
from datetime import datetime, timezone

import numpy as np

from app.assess.models import Cluster, Evidence, PairResult, Question, SharedItem
from app.assess.similarity import (CohortPaper, apply_verdict, class_outliers, example_clusters, final_value, find_quote,
                                   gram_counts, pair_results, shared_rarely)

OPEN = Question(id="q9", label="9", type="open", points=6, prompt="Εξηγήστε πώς λειτουργεί η quicksort.",
                model_answer="Επιλέγουμε άξονα και διαμερίζουμε τον πίνακα.")
MCS = [Question(id=f"m{i}", label=f"M{i}", type="multiple_choice", points=1, answer="α",
                options=["α) a", "β) b", "γ) c", "δ) d"]) for i in range(6)]
QUESTIONS = [OPEN, *MCS]
COMMON = "η quicksort είναι αλγόριθμος ταξινόμησης που ακολουθεί τη στρατηγική διαίρει και βασίλευε"
INDEPENDENT = [
    "Παίρνουμε το πρώτο στοιχείο σαν pivot και μετακινούμε τα μικρότερα αριστερά του, μετά επαναλαμβάνουμε σε κάθε κομμάτι.",
    "Ο αλγόριθμος διαλέγει τυχαία ένα στοιχείο, φτιάχνει δύο λίστες με τα μικρότερα και τα μεγαλύτερα και τις ενώνει στο τέλος.",
    "Χωρίζουμε τον πίνακα με βάση έναν άξονα ώστε δεξιά να είναι τα μεγάλα, μετά καλούμε την ίδια συνάρτηση για τα δύο μισά.",
    "Βάζουμε δύο δείκτες από τις άκρες που πλησιάζουν και ανταλλάσσουν στοιχεία μέχρι να συναντηθούν, μετά αναδρομή.",
    "Επιλέγω το τελευταίο στοιχείο, κάνω partition κατά Lomuto και συνεχίζω αναδρομικά αριστερά και δεξιά του άξονα.",
    "Το pivot μπαίνει στη σωστή του θέση σε κάθε βήμα και έτσι μετά από n βήματα όλος ο πίνακας είναι ταξινομημένος.",
]
COPIED = ("Ο Hoare πρότεινε δύο δείκτες που κινούνται ο ένας προς τον άλλον και όταν βρουν στοιχεία σε λάθος πλευρά τα "
          "ανταλλάσσουν, έτσι στο παράδειγμα [7, 2, 9, 4] μετά το πρώτο πέρασμα έχουμε [4, 2, 7, 9]")


def ink(seed: int, template: np.ndarray, blob_at: tuple[int, int] | None = None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = template.copy()
    y, x = blob_at or (int(rng.integers(5, 50)), int(rng.integers(5, 36)))
    img[y:y + 6, x:x + 10] += rng.uniform(0.4, 0.9, (6, 10)).astype(np.float32)
    img[int(rng.integers(5, 55)), :] += 0.2
    return np.clip(img, 0, 1)


def cohort():
    template = np.zeros((64, 48), np.float32)
    template[2:4, :] = 1.0  # the printed header every page has
    template[30, :] = 1.0
    papers = []
    for i in range(8):
        answer = COMMON + ". " + (INDEPENDENT[i] if i < len(INDEPENDENT) else COPIED)
        finals = {q.id: ("0", True) for q in MCS}
        papers.append(CohortPaper(id=f"p{i}", name=f"Φοιτητής {i}", answers={OPEN.id: answer}, finals=finals,
                                  pages=[(1, f"{i:016x}", ink(i, template))]))
    papers[0].answers[OPEN.id] = COMMON + ". " + COPIED + " και αυτό είναι όλο"  # p0 copies p6/p7's distinctive answer
    for q, wrong in zip(MCS[:4], ["3", "2", "3", "1"]):  # p2 and p3 share four rare wrong answers
        papers[2].finals[q.id] = (wrong, False)
        papers[3].finals[q.id] = (wrong, False)
    papers[4].finals[MCS[5].id] = ("1", False)  # one common-ish wrong answer elsewhere
    papers[5].pages = [(1, papers[1].pages[0][1], papers[1].pages[0][2].copy())]  # p5 hands in p1's scanned page
    return papers


def score(results, a, b):
    key = (min(a, b), max(a, b))
    return next((p.score for p in results if (p.a, p.b) == key), 0)


def test_copies_score_high_and_independent_pairs_low():
    results = pair_results(cohort(), QUESTIONS, [])
    assert score(results, "p0", "p6") >= 60 and score(results, "p0", "p7") >= 60
    assert 30 <= score(results, "p2", "p3") < 60  # four identical rare wrong choices in a class of eight: worth a look
    assert score(results, "p1", "p5") >= 90
    assert all(p.score < 30 for p in results if (p.a, p.b) not in {("p0", "p6"), ("p0", "p7"), ("p6", "p7"),
                                                                    ("p2", "p3"), ("p1", "p5")})


def test_common_phrases_ignored():
    results = pair_results(cohort(), QUESTIONS, [])
    for p in results:
        for e in p.evidence:
            if e.code == "shared_passage":
                assert all("διαίρει και βασίλευε" not in x for x in e.detail["passages"])


def test_template_removed_from_layout():
    papers = cohort()
    results = pair_results(papers, QUESTIONS, [])
    layout = [p for p in results if any(e.code in ("page_layout", "same_page_image") for e in p.evidence)]
    assert [(p.a, p.b) for p in layout] == [("p1", "p5")]


def test_shared_rare_mistakes_and_details():
    papers = cohort()
    clusters = [Cluster(question_id="q9", kind="mistake", label="Λέει ότι η χειρότερη είναι O(n log n)", members=["p1", "p4"]),
                Cluster(question_id="q9", kind="detail", label="Ίδιο παράδειγμα [7,2,9,4]", members=["p1", "p4"]),
                Cluster(question_id="q9", kind="mistake", label="Συνηθισμένο λάθος", members=[f"p{i}" for i in range(6)])]
    results = pair_results(papers, QUESTIONS, clusters)
    pair = next(p for p in results if (p.a, p.b) == ("p1", "p4"))
    assert {e.code for e in pair.evidence} >= {"shared_mistake", "shared_detail"} and pair.score >= 30
    assert score(results, "p0", "p1") < 30  # the misconception half the class shares is not evidence


def test_documents_ids_authors_and_files():
    papers = [CohortPaper(id=f"d{i}", name=n, kind="typed", file_id=f"id{i}", author="", sha256=f"h{i}")
              for i, n in enumerate(["Άννα Β.", "Βασίλης Γ.", "Γιάννης Δ.", "Δήμητρα Ε.", "Ελένη Ζ."])]
    papers[1].file_id = "id0"
    papers[2].author = papers[3].author = "Άννα Βλάχου"
    papers[4].sha256 = "h0"
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    results = pair_results(papers, QUESTIONS, [])
    codes = {(p.a, p.b): {e.code for e in p.evidence} for p in results}
    assert "same_document_id" in codes[("d0", "d1")]
    assert "same_author" in codes[("d2", "d3")]
    authored = {(p.a, p.b): e for p in results for e in p.evidence if e.code == "author_is_student"}
    assert set(authored) == {("d0", "d2"), ("d0", "d3")} and authored[("d0", "d2")].strength == 0.85  # Άννα's name on their files
    assert "same_file" in codes[("d0", "d4")] and score(results, "d0", "d4") == 100
    papers[1].split = True  # parts of one scanned batch share the batch's IDs: not evidence
    assert "same_document_id" not in {e.code for p in pair_results(papers, QUESTIONS, []) for e in p.evidence}
    del now


def test_verdict_moves_the_score():
    pair = PairResult(a="x", b="y", score=40, evidence=[Evidence(code="shared_passage", strength=0.4)])
    assert apply_verdict(pair, "likely_copied", "Ίδιες φράσεις.").score == 75
    assert apply_verdict(pair, "independent", "").score == 40  # a long shared passage is not talked away
    weak = PairResult(a="x", b="y", score=40, evidence=[Evidence(code="shared_passage", strength=0.2),
                                                         Evidence(code="similar_style", strength=0.2)])
    assert apply_verdict(weak, "independent", "Διαφορετικές λύσεις.").score == 22
    hard = PairResult(a="x", b="y", score=100, evidence=[Evidence(code="same_file", strength=1.0)])
    assert apply_verdict(hard, "independent", "").score == 100


def test_final_values():
    tf = Question(id="t", label="t", type="true_false", points=1, answer="true")
    num = Question(id="n", label="n", type="numeric", points=1, answer="1")
    assert final_value(tf, "Σ") == "true" and final_value(tf, "") is None
    assert final_value(MCS[0], "β") == "1" and final_value(num, "0,50") == "0.5"


def test_class_outliers():
    random.seed(1)
    papers = [CohortPaper(id=f"p{i}", answers={OPEN.id: " ".join(random.choice(["γρήγορη", "λίστα", "άξονας", "πίνακας"])
                                                                for _ in range(20))}) for i in range(8)]
    papers[0].answers[OPEN.id] = " ".join(["πολυπαραγοντική", "αλληλεπιδραστικότητα", "αποτελεσματικότητας"] * 30)
    out = class_outliers(papers, QUESTIONS)
    assert list(out) == ["p0"] and out["p0"][0]["question"] == "9"


def test_possibly_stays_below_likely():
    pair = PairResult(a="x", b="y", score=80, evidence=[Evidence(code="shared_passage", strength=0.8)])
    assert apply_verdict(pair, "possibly", "").score == 59
    hard = PairResult(a="x", b="y", score=100, evidence=[Evidence(code="same_file", strength=1.0)])
    assert apply_verdict(hard, "possibly", "").score == 100


def cluster(strength: float, code: str = "shared_detail", label: str = "[9, 4, 7, 1]", size: int = 2) -> Evidence:
    return Evidence(code=code, strength=strength, detail={"labels": [label], "sizes": [size]})


def test_likely_needs_two_coincidences_or_strong_evidence():
    one = PairResult(a="x", b="y", score=40, evidence=[cluster(0.4)])
    assert apply_verdict(one, "likely_copied", "").score == 55  # one shared example: worth a look, not "likely"
    two = PairResult(a="x", b="y", score=58, evidence=[cluster(0.4), cluster(0.3, "shared_mistake", "μόνο ανάποδα")])
    assert apply_verdict(two, "likely_copied", "").score == 75
    passage = PairResult(a="x", b="y", score=39, evidence=[Evidence(code="shared_passage", strength=0.39)])
    assert apply_verdict(passage, "likely_copied", "").score == 75
    quoted = [SharedItem(what="ίδιο παράδειγμα", a="[9, 4, 7, 1] παίρνουμε", b="[9, 4, 7, 1] παίρνουμε", rare=True),
              SharedItem(what="ίδιο λάθος", a="μόνο όταν είναι ανάποδα", b="μόνο σε αντίστροφη σειρά", rare=True)]
    assert apply_verdict(one, "likely_copied", "", quoted).score == 75  # two rare things found in both, checked
    common = [x.model_copy(update={"rare": False}) for x in quoted]
    assert apply_verdict(one, "likely_copied", "", common).score == 55
    assert apply_verdict(two, "independent", "").score == 58  # strong evidence is not talked away
    assert apply_verdict(one, "independent", "").score == 24
    crowd = PairResult(a="x", b="y", score=45, evidence=[cluster(0.3, size=5), cluster(0.22, "shared_mistake", size=5)])
    assert apply_verdict(crowd, "likely_copied", "").score == 59  # what five papers share says little about two


def test_same_wrong_answers_are_judged_against_chance():
    """Weak students share wrong answers by chance (on true/false they cannot help it); what counts is rare wrong
    answers matched beyond what chance explains in a class this size."""
    rng = random.Random(3)
    tf = [Question(id=f"t{i}", label=f"T{i}", type="true_false", points=1, answer="Σ") for i in range(6)]
    mc = [Question(id=f"m{i}", label=f"M{i}", type="multiple_choice", points=1, answer="α", options=["α", "β", "γ", "δ"])
          for i in range(6)]
    num = [Question(id=f"n{i}", label=f"N{i}", type="numeric", points=1, answer="10") for i in range(4)]
    papers = []
    for i in range(40):
        skill = rng.uniform(0.3, 0.95)
        finals = {}
        for q in tf + mc + num:
            if rng.random() < skill:
                finals[q.id] = ({"true_false": "true", "multiple_choice": "0", "numeric": "10"}[q.type], True)
            else:
                finals[q.id] = ({"true_false": "false", "multiple_choice": str(rng.randint(1, 3)),
                                 "numeric": rng.choice(["9", "11", "100", "1024", "12", "20"])}[q.type], False)
        papers.append(CohortPaper(id=f"p{i:02d}", finals=finals))
    source = papers[0]
    source.finals.update({"t0": ("false", False), "t1": ("false", False), "m0": ("2", False), "m1": ("3", False),
                          "n0": ("37", False), "n1": ("512", False), "n2": ("0.5", False)})
    papers.append(CohortPaper(id="copier", finals=dict(source.finals)))
    results = pair_results(papers, tf + mc + num, [])
    assert score(results, "p00", "copier") >= 80
    assert max((p.score for p in results if (p.a, p.b) != ("copier", "p00")), default=0) < 30

    # Wrong on the same true/false questions everyone else gets right: a little odd, never "worth a look" alone.
    pair = [CohortPaper(id=f"w{i}", finals={q.id: ("false", False) for q in tf}) for i in range(2)]
    rest = [CohortPaper(id=f"r{i}", finals={q.id: ("true", True) for q in tf}) for i in range(8)]
    assert score(pair_results(pair + rest, tf, []), "w0", "w1") < 30


def test_find_quote_checks_the_model_citations():
    text = "Διαλέγουμε ως άξονα το μεσαίο στοιχείο, και στο παράδειγμα [9, 4, 7, 1] παίρνουμε [1, 4, 7, 9]."
    assert find_quote("στο παράδειγμα [9,4,7,1] παίρνουμε", text) == "στο παράδειγμα [9, 4, 7, 1] παίρνουμε"
    assert find_quote("ΔΙΑΛΕΓΟΥΜΕ ΩΣ ΑΞΟΝΑ", text) == "Διαλέγουμε ως άξονα"
    assert find_quote("και στο παράδειγμα [9, 4, 7, 1] βγάζουμε", text) == "και στο παράδειγμα [9, 4, 7, 1"  # a word off
    assert find_quote("ο άξονας είναι πάντα το τελευταίο στοιχείο", text) is None  # not what the paper says
    assert find_quote("[9, 4]", text) is None  # too short to tell


def test_the_same_example_values_are_a_detail():
    texts = {"p0": "Στο παράδειγμα [9, 4, 7, 1] ο άξονας είναι το 4.", "p1": "π.χ. στον πίνακα 9,4,7,1 → 1,4,7,9",
             "p2": "Ταξινομούμε τον [1, 2, 3, 4] σε βήματα 3, 3, 3.", "p3": "Για 1, 2, 3, 4 δεν αλλάζει τίποτα.",
             "p4": "Το [5, 3, 8] του φυλλαδίου γίνεται [3, 5, 8].", "p5": "Παίρνουμε [5, 3, 8] όπως στην εκφώνηση."}
    papers = [CohortPaper(id=k, answers={OPEN.id: v}) for k, v in texts.items()] + \
        [CohortPaper(id=f"x{i}", answers={OPEN.id: "Διαμέριση και αναδρομή."}) for i in range(6)]
    exam = "Ταξινομήστε τον πίνακα [5, 3, 8]."
    found = example_clusters(papers, QUESTIONS, [], exam)
    assert [(c.members, c.label, c.kind) for c in found] == [(["p0", "p1"], "[9, 4, 7, 1]", "detail")]  # not counting, not the exam's
    model = Cluster(question_id=OPEN.id, kind="detail", label="ίδιο παράδειγμα", members=["p0", "p1"])
    assert example_clusters(papers, QUESTIONS, [model], exam) == []  # the model's grouping already has it


def test_what_two_quotes_share_must_be_theirs_alone():
    texts = ["Στο παράδειγμα [9, 4, 7, 1] ο άξονας είναι το 4, τα μικρότερα πάνε αριστερά και τα μεγαλύτερα δεξιά.",
             "Για [9, 4, 7, 1] παίρνω το 4 και βάζω τα μικρότερα αριστερά και τα μεγαλύτερα δεξιά.",
             *["Ο άξονας χωρίζει: τα μικρότερα αριστερά και τα μεγαλύτερα δεξιά, μετά αναδρομή."] * 4]
    counts = gram_counts([CohortPaper(id=f"p{i}", answers={OPEN.id: t}) for i, t in enumerate(texts)])
    assert shared_rarely("στο παράδειγμα [9, 4, 7, 1] ο άξονας", "Για [9, 4, 7, 1] παίρνω", counts)  # their example
    assert not shared_rarely("τα μικρότερα πάνε αριστερά και τα μεγαλύτερα δεξιά",
                             "βάζω τα μικρότερα αριστερά και τα μεγαλύτερα δεξιά", counts)  # what everyone writes
    assert not shared_rarely("ο άξονας είναι το 4", "παίρνω το 4", counts)  # nothing in common to check


def test_verdict_spellings():
    from app.assess.classwork import verdict_of
    assert [verdict_of(x) for x in ("likely_copied", "Likely copied", "possibly copied", "Unlikely copied", "independent",
                                    "not copied", "maybe")] == \
        ["likely_copied", "likely_copied", "possibly", "independent", "independent", "independent", ""]


def test_groups_seen_twice_are_merged():
    from app.assess.classwork import merge_clusters
    found = [Cluster(question_id="q9", kind="mistake", label="μόνο ανάποδα", members=["p6", "p7"]),
             Cluster(question_id="q9", kind="detail", label="[9, 4, 7, 1]", members=["p6", "p7"]),
             Cluster(question_id="q9", kind="mistake", label="μόνο σε αντίστροφη σειρά", members=["p6", "p7"]),
             Cluster(question_id="q9", kind="detail", label="pivot 5", members=["p1", "p2", "p3"]),
             Cluster(question_id="q9", kind="detail", label="ο αριθμός 5", members=["p2", "p3", "p4"])]
    assert [(c.kind, c.label, c.members) for c in merge_clusters(found)] == [
        ("mistake", "μόνο ανάποδα", ["p6", "p7"]), ("detail", "[9, 4, 7, 1]", ["p6", "p7"]),
        ("detail", "pivot 5", ["p1", "p2", "p3", "p4"])]


def test_a_detail_many_share_says_little_about_two():
    papers = [CohortPaper(id=f"p{i:02d}") for i in range(36)]
    two = Cluster(question_id="q9", kind="detail", label="[9, 4, 7, 1]", members=["p00", "p01"])
    four = Cluster(question_id="q9", kind="detail", label="pivot 5", members=["p10", "p11", "p12", "p13"])
    results = pair_results(papers, QUESTIONS, [two, four])
    assert score(results, "p00", "p01") == 40 and score(results, "p10", "p11") < 25  # not even worth a check
