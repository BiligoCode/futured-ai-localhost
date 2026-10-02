from datetime import datetime, timezone

from app.assess.models import Block, PageReading, Paper
from app.assess.signals import ai_analysis, sophistication, strip_exam_lines, student_text, with_class_signal

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)

HUMAN_EL = ("Η quicksort παίρνει ένα στοιχείο για pivot, συνήθως το πρώτο. Μετά βάζουμε αριστερά όσα είναι μικρότερα και "
            "δεξιά όσα είναι μεγαλύτερα. Ξανακάνουμε το ίδιο σε κάθε κομμάτι μέχρι να μείνει ένα στοιχείο. Αν ο πίνακας "
            "είναι ήδη ταξινομημένος και παίρνουμε πάντα το πρώτο, κάθε φορά φεύγει μόνο ένα στοιχείο, άρα κάνουμε "
            "n-1, n-2 κλπ συγκρίσεις και βγαίνει O(n^2). Στη μέση περίπτωση είναι n log n γιατί χωρίζεται περίπου στη μέση. "
            "Δεν θυμάμαι ακριβώς την απόδειξη για τη μέση περίπτωση αλλά έχει να κάνει με το ότι το βάθος είναι log n.")

AI_EN = ("Quicksort is a pivotal divide-and-conquer algorithm that showcases the intricate interplay between partitioning "
         "and recursion — a testament to its enduring relevance. It is important to note that the choice of pivot plays a "
         "crucial role in its performance. Furthermore, the algorithm leverages in-place partitioning, which underscores its "
         "memory efficiency. Moreover, it delves into the realm of average-case analysis — where it truly shines. "
         "Additionally, randomized pivots foster robust performance across a myriad of inputs. In conclusion, quicksort "
         "remains a comprehensive and invaluable tool — not only efficient but also elegant. Overall, its multifaceted "
         "design is noteworthy, and its seamless integration into standard libraries is commendable.")


def test_human_greek_answer_scores_low():
    ai = ai_analysis(HUMAN_EL, typed=False)
    assert ai.level == "low" and ai.score < 30


def test_ai_english_typed_answer_scores_strong():
    ai = ai_analysis(AI_EN, typed=True, likelihood=85, reasons=["Υπερβολικά γυαλισμένο ύφος"])
    codes = {s.code for s in ai.signals}
    assert {"ai_vocabulary", "em_dash", "formulaic", "lara_reading"} <= codes
    assert next(s for s in ai.signals if s.code == "lara_reading").strength < 0.2  # weak on its own
    assert ai.level == "strong" and ai.score >= 60 and ai.note == "Υπερβολικά γυαλισμένο ύφος"
    assert ai.signals == sorted(ai.signals, key=lambda s: -s.strength)


def test_em_dashes_do_not_count_on_handwriting():
    assert "em_dash" not in {s.code for s in ai_analysis(AI_EN, typed=False).signals}


def test_artifacts_are_near_proof_even_on_short_text():
    ai = ai_analysis("Sure! Here's a revised version of your answer: O(n log n).", typed=True)
    assert ai.level == "strong" and ai.score >= 85
    ai = ai_analysis("Δες εδώ: https://el.wikipedia.org/wiki/Quicksort?utm_source=chatgpt.com", typed=True)
    assert ai.signals[0].code == "citation_artifact"


def test_short_text_is_insufficient():
    ai = ai_analysis("Σ, β, 208", typed=False, likelihood=90)
    assert ai.level == "insufficient" and ai.score <= 25


def test_invisible_characters_on_typed_text():
    text = HUMAN_EL.replace(" ", " ", 4)
    ai = ai_analysis(text, typed=True)
    assert any(s.code == "invisible_chars" and s.strength == 0.45 for s in ai.signals)
    ai = ai_analysis(HUMAN_EL + "​", typed=True)
    assert any(s.code == "invisible_chars" and s.strength == 0.6 for s in ai.signals)


def test_greek_ai_phrasing_counts():
    greek_ai = ("Συμπερασματικά, η quicksort διαδραματίζει καθοριστικό ρόλο στην ταξινόμηση. Είναι σημαντικό να σημειωθεί "
                "ότι η επιλογή του άξονα υπογραμμίζει την πολυδιάστατη φύση του αλγορίθμου, ενώ αναδεικνύει την ολιστική "
                "προσέγγιση του διαίρει και βασίλευε. Επιπροσθέτως, αξιοποιώντας την αναδρομή, εμβαθύνει σε ένα ευρύ φάσμα "
                "περιπτώσεων. Όχι μόνο είναι γρήγορη αλλά και κομψή, αποτελώντας ακρογωνιαίο λίθο της επιστήμης υπολογιστών. "
                "Αξίζει να αναφερθεί ότι η πληθώρα των εφαρμογών της είναι αδιαμφισβήτητη. Συνοψίζοντας, πρόκειται για "
                "καίριας σημασίας εργαλείο.")
    ai = ai_analysis(greek_ai, typed=True)
    assert ai.score >= 60 and {"ai_vocabulary", "formulaic"} <= {s.code for s in ai.signals}


def test_student_text_strips_exam_lines_struck_text_and_markers():
    paper = Paper(id="p", created_at=NOW, filename="x", reading=[
        PageReading(n=1, text="Θέμα 1. Εξηγήστε πώς λειτουργεί η quicksort και γιατί είναι γρήγορη.\nΗ δική μου απάντηση εδώ."),
        PageReading(n=2, blocks=[Block(label="2", text="~~λάθος~~ σωστό (circled: β) [figure: δέντρο]")]),
    ])
    text, typed = student_text(paper, "Θέμα 1. Εξηγήστε πώς λειτουργεί η quicksort και γιατί είναι γρήγορη.")
    assert "Εξηγήστε" not in text and "Η δική μου απάντηση" in text
    assert "λάθος" not in text and "circled" not in text and "δέντρο" not in text and "σωστό" in text
    assert typed is True
    assert strip_exam_lines("a b c", "") == "a b c"


def test_class_signal_is_added_and_refreshed():
    ai = ai_analysis(HUMAN_EL, typed=False)
    raised = with_class_signal(ai, [{"question": "4", "length_z": 3.1}])
    assert raised.score > ai.score and raised.signals[0].code in ("over_elaborate",) or any(s.code == "over_elaborate" for s in raised.signals)
    assert with_class_signal(raised, []).score == ai.score


def test_sophistication_orders_registers():
    assert sophistication(AI_EN) > sophistication("it is fast and it splits the list in two parts")
    assert sophistication("") == 0


def test_lara_estimate_counts_only_against_the_class():
    plain = ai_analysis(HUMAN_EL, typed=True, likelihood=95)
    everyone_high = with_class_signal(plain, [], class_likelihood=95)
    assert not any(s.code in ("lara_reading", "lara_vs_class") for s in everyone_high.signals)
    stands_out = with_class_signal(plain, [], class_likelihood=10)
    sig = next(s for s in stands_out.signals if s.code == "lara_vs_class")
    assert sig.detail == {"likelihood": 95, "class_median": 10} and sig.strength > 0.3


def test_a_repeated_technical_term_is_not_ai_vocabulary():
    text = ("Η βελτιστοποίηση είναι ο στόχος. " * 4) + HUMAN_EL
    assert "ai_vocabulary" not in {s.code for s in ai_analysis(text, typed=True).signals}
