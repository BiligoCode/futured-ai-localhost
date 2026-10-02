import pytest

from app.assess.answers import (is_blank, normalize_text, numbers_match, option_letter, option_text, parse_choices,
                                parse_numbers, parse_true_false, short_matches)


def test_normalize_text_ignores_case_accents_final_sigma_and_struck_text():
    assert normalize_text("  ΛΆΘΟΣ  ") == "λαθοσ"
    assert normalize_text("Σωστός") == "σωστοσ"
    assert normalize_text("~~200~~ 208") == "208"


@pytest.mark.parametrize("final,expected", [
    ("Σ", True), ("σ", True), ("Σωστό", True), ("ΣΩΣΤΟ", True), ("(circled: Σωστό)", True), ("(ticked: Σ)", True),
    ("Α", True), ("Αληθές", True), ("True", True), ("T", True), ("✓", True), ("yes", True),
    ("Λ", False), ("Λάθος", False), ("λαθος", False), ("Ψ", False), ("Ψευδές", False), ("False", False), ("F", False),
    ("✗", False), ("Λάθος, το σωστό είναι O(n log n)", False), ("not true", False),
    ("", None), (None, None), ("?", None), ("ίσως", None),
])
def test_parse_true_false(final, expected):
    assert parse_true_false(final) is expected


def test_struck_answer_does_not_count():
    assert parse_true_false("~~Σ~~ Λ") is False


OPTIONS = ["α) O(n)", "β) O(n log n)", "γ) O(n^2)", "δ) O(log n)"]


@pytest.mark.parametrize("final,expected", [
    ("β", {1}), ("Β", {1}), ("(β)", {1}), ("β)", {1}), ("β΄", {1}), ("b", {1}), ("B", {1}),
    ("β) O(n log n)", {1}), ("(circled: γ)", {2}), ("η απάντηση είναι β", {1}), ("α, γ", {0, 2}),
    ("O(n log n)", {1}), ("o(nlogn)", {1}), ("~~γ~~ β", {1}),
    ("", None), ("δεν ξέρω", None), ("2", None),
])
def test_parse_choices(final, expected):
    got = parse_choices(final, OPTIONS)
    assert (set(got) if got is not None else None) == expected


def test_numbered_options_accept_digits():
    assert parse_choices("2", ["1. πρώτο", "2. δεύτερο", "3. τρίτο"]) == frozenset({1})


def test_key_letters_and_student_letters_meet_across_scripts():
    assert parse_choices("β", OPTIONS) == parse_choices("b", OPTIONS)
    assert option_letter(1, "β") == "β" and option_letter(2, "c") == "c"
    assert option_text("β) O(n log n)") == "O(n log n)"


@pytest.mark.parametrize("final,expected", [
    ("208", [208.0]), ("858 - 650 = 208", [208.0]), ("208 βιβλία", [208.0]), ("x = -3", [-3.0]), ("−5", [-5.0]),
    ("0,5", [0.5]), ("3,14", [3.14]), ("0.007", [0.007]), ("0,500", [0.5]), ("1.2345", [1.2345]),
    ("1.000", [1000.0, 1.0]), ("1,000", [1000.0, 1.0]), ("12.500", [12500.0, 12.5]), ("1.234,56", [1234.56]),
    ("1,234.56", [1234.56]), ("12 500", [12500.0]),
    ("7/1000", [0.007]), ("x = 1/2", [0.5]), ("7e-3", [0.007]), ("7·10^-3", [0.007]), ("7×10⁻³", [0.007]),
    ("10^3", [1000.0]), ("42%", [42.0, 0.42]), ("2,5 m/s", [2.5]),
    ("", []), (None, []), ("δεν ξέρω", []),
])
def test_parse_numbers(final, expected):
    got = parse_numbers(final)
    assert len(got) == len(expected)
    assert all(g == pytest.approx(e) for g, e in zip(got, expected))


def test_numbers_match_with_tolerance():
    assert numbers_match([3.14], 3.14159, 0.01)
    assert not numbers_match([3.1], 3.14159, 0.01)
    assert numbers_match([0.1 + 0.2], 0.3, 0)
    assert numbers_match([1.0, 1000.0], 1000, 0)


@pytest.mark.parametrize("final,key,expected", [
    ("O(n log n)", "O(n log n)", True), ("o(nlogn)", "O(n log n)", True), ("n log n", "O(n log n) | n log n", True),
    ("Μιτοχόνδρια", "μιτοχονδρια", True), ("O(n²)", "O(n^2)", True), ("O(n)", "O(n log n)", False), ("", "x", False),
])
def test_short_matches(final, key, expected):
    assert short_matches(final, key) is expected


def test_is_blank():
    assert is_blank(None) and is_blank("") and is_blank(" — ") and is_blank("null")
    assert not is_blank("β") and not is_blank("0")


def test_lone_letter_beyond_listed_options_still_counts():
    assert parse_choices("γ", ["α) x", "β) y"]) == frozenset({2})
    assert parse_choices("η σωστή είναι η β", ["α) x", "β) y"]) == frozenset({1})
