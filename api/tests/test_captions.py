from app.captions import LINE_CHARS, cues_from_alignment, cues_from_text, to_ass


def alignment_for(text: str, per_char: float = 0.06) -> dict:
    return {"characters": list(text),
            "character_start_times_seconds": [i * per_char for i in range(len(text))],
            "character_end_times_seconds": [(i + 1) * per_char for i in range(len(text))]}


def test_cues_follow_sentences_and_speech_timing():
    text = "Έχουμε έναν ταξινομημένο πίνακα. Ψάχνουμε το 23;"
    cues = cues_from_alignment(alignment_for(text))
    assert [c.text for c in cues] == ["Έχουμε έναν ταξινομημένο πίνακα.", "Ψάχνουμε το 23;"]
    second = text.index("Ψ") * 0.06
    assert cues[0].start == 0 and abs(cues[1].start - second) < 1e-6
    assert cues[0].end == cues[1].start  # stays up until the next caption


def test_long_sentences_split_into_two_line_cues():
    text = " ".join(["δυναμικός προγραμματισμός"] * 8) + "."
    cues = cues_from_alignment(alignment_for(text, 0.02))
    assert len(cues) > 1
    for c in cues:
        lines = c.text.split("\n")
        assert len(lines) <= 2 and all(len(line) <= LINE_CHARS for line in lines)


def test_untimed_cues_cover_the_audio():
    cues = cues_from_text("Πρώτη πρόταση. Δεύτερη πρόταση.", 4.0)
    assert len(cues) == 2 and cues[0].start == 0 and abs(cues[-1].end - 4.0) < 1e-6


def test_ass_output():
    ass = to_ass(cues_from_text("Γεια {σας}.", 1.5))
    assert "Style: Caption,DejaVu Sans" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:01.50,Caption,,0,0,0,,Γεια (σας)." in ass


def test_no_one_word_leftovers_and_abbreviations_do_not_end_cues():
    text = ("Φτιάχνουμε πίνακα dp, όπου το dp αποθηκεύει το ελάχιστο πλήθος νομισμάτων για το ποσό i. "
            "Χρειαζόμαστε δύο νομίσματα, π.χ. 3 συν 3.")
    cues = cues_from_alignment(alignment_for(text, 0.03))
    assert min(len(c.text.split()) for c in cues) >= 3, [c.text for c in cues]
    assert any("π.χ. 3 συν 3." in c.text.replace("\n", " ") for c in cues)
