import json

import pytest

from app.assess.models import Block, PageReading
from app.assess.reading import ReadingError, parse_page, printed_check, read_page, reading_text, student_identity
from tests.fakes import FnVision

PAGE = {"student_name": "Μαρία Κ.", "student_id": "1115201900123",
        "blocks": [{"label": "1", "prompt": "Η δυαδική αναζήτηση …", "text": "(circled: Σωστό)", "final": "Σ"},
                   {"label": "3", "text": "858 - 650 = 208", "final": "208"},
                   {"label": None, "text": "   ", "final": None}],
        "notes": "Q3: last digit overwritten"}


def test_parse_page_keeps_blocks_and_drops_empty_ones():
    page, name, sid = parse_page("```json\n" + json.dumps(PAGE, ensure_ascii=False) + "\n```", 1)
    assert (name, sid) == ("Μαρία Κ.", "1115201900123")
    assert [(b.label, b.final) for b in page.blocks] == [("1", "Σ"), ("3", "208")]
    assert page.notes == "Q3: last digit overwritten"


def test_parse_page_tolerates_loose_shapes():
    page, name, sid = parse_page(json.dumps({"student_name": "null", "blocks": ["free text answer"], "notes": ["a", "b"]}), 2)
    assert name is None and page.blocks[0].text == "free text answer" and page.notes == "a; b"
    page, _, _ = parse_page(json.dumps([{"label": 2, "text": "x", "final": 5}]), 1)
    assert page.blocks[0].label == "2" and page.blocks[0].final == "5"


def test_read_page_retries_once_then_fails():
    replies = iter(["not json at all", json.dumps(PAGE, ensure_ascii=False)])
    vision = FnVision(lambda s, p, imgs: next(replies))
    page, name, _ = read_page(vision, b"jpeg", 1, 2)
    assert name == "Μαρία Κ." and len(vision.calls) == 2 and "not valid JSON" in vision.calls[1][1]
    assert "page 1 of 2" in vision.calls[0][1] and vision.calls[0][2] == 1
    with pytest.raises(ReadingError, match="page 4"):
        read_page(FnVision(lambda s, p, i: "nope"), b"jpeg", 4, 4)


def test_reading_prompt_never_mentions_a_key():
    vision = FnVision(lambda s, p, i: json.dumps(PAGE))
    read_page(vision, b"jpeg", 1, 1)
    system, prompt, _ = vision.calls[0]
    assert "key" not in (system + prompt).lower().replace("keyboard", "")


def test_reading_text_and_identity():
    pages = [PageReading(n=1, blocks=[Block(label="1", text="(circled: Σωστό)", final="Σ")], notes="n"),
             PageReading(n=2, text="Typed answer for question 2")]
    text = reading_text(pages)
    assert "--- page 1 ---\n[1] (circled: Σωστό) ⟶ final: Σ\n(reader's notes: n)" in text
    assert "--- page 2 ---\nTyped answer for question 2" in text
    assert student_identity([(None, None), ("Νίκος", None), ("Άλλος", "42")]) == ("Νίκος", "42")


ANSWER = "Βάζουμε ένα στοιχείο σαν pivot και ό,τι είναι μικρότερο πάει αριστερά του. Είναι γρήγορη αλγόριθμος."
QUESTION = "Η δυαδική αναζήτηση απαιτεί ταξινομημένο πίνακα (Σωστό ή Λάθος)"


def test_an_answer_filed_as_the_printed_question_stays_the_students():
    reply = json.dumps({"blocks": [
        {"label": "Θέμα 5", "prompt": ANSWER, "text": "Είναι γρήγορη αλγόριθμος."},  # the reader split the answer
        {"label": "1", "prompt": QUESTION, "text": "Σ", "final": "Σ"},
        {"label": "2", "prompt": "Εξηγήστε πώς λειτουργεί η quicksort", "text": "λειτουργεί η quicksort αναδρομικά"},
    ]}, ensure_ascii=False)
    page, _, _ = parse_page(reply, 1)
    assert (page.blocks[0].prompt, page.blocks[0].text) == (None, ANSWER)
    assert (page.blocks[1].prompt, page.blocks[1].text) == (QUESTION, "Σ")
    assert page.blocks[2].prompt == "Εξηγήστε πώς λειτουργεί η quicksort"  # not at either end: stays printed


def test_printed_text_is_checked_against_the_exam():
    page = PageReading(n=1, blocks=[Block(label="1", prompt=QUESTION, text="Σ", final="Σ"),
                                    Block(label="5", prompt="Βάζουμε ένα στοιχείο σαν pivot και", text="μετά αναδρομή.")])
    printed = printed_check("Θέμα 1. " + QUESTION + " Θέμα 5. Εξηγήστε πώς λειτουργεί η quicksort.")
    text = reading_text([page], printed=printed)
    assert "[1] Σ ⟶ final: Σ" in text and QUESTION not in text
    assert "[5] Βάζουμε ένα στοιχείο σαν pivot και μετά αναδρομή." in text  # not printed in the exam: the student's
    assert "(printed: " + QUESTION + ")" in reading_text([page], show_printed=True)
    assert printed_check("") is None and "Βάζουμε" not in reading_text([page])


def test_an_answer_filed_entirely_as_printed_text_is_kept():
    reply = json.dumps({"blocks": [{"label": "Θέμα 4", "prompt": "ευστάθεια", "text": "", "final": None},
                                   {"label": "Θέμα 5", "prompt": ANSWER, "text": ""},
                                   {"label": "Θέμα 6", "prompt": "Περιγράψτε τη BFS.", "text": ""}]}, ensure_ascii=False)
    page, _, _ = parse_page(reply, 1)
    assert [b.label for b in page.blocks] == ["Θέμα 4", "Θέμα 5", "Θέμα 6"]
    printed = printed_check("Θέμα 4: Ποια ιδιότητα … ; Θέμα 5: Εξηγήστε την quicksort. Θέμα 6: Περιγράψτε τη BFS. "
                            "Λύσεις: 4. ευστάθεια")  # the key printed in the solutions does not hide the answer
    text = reading_text([page], printed=printed)
    assert "[Θέμα 4] ευστάθεια" in text and f"[Θέμα 5] {ANSWER}" in text
    assert "[Θέμα 6]\n" in text + "\n" and "BFS" not in text  # printed and unanswered: no answer
    assert "[Θέμα 4] ευστάθεια" in reading_text([page])  # nothing to check against: the reader listed it as answered
