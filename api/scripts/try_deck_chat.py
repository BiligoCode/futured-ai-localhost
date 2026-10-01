"""Run the slides assistant against the real model on a sample Greek deck, to tune the prompt.

    uv run python scripts/try_deck_chat.py            # three mixed requests
    uv run python scripts/try_deck_chat.py "κάνε τους τίτλους κόκκινους"

Prints the reply, the edit log and the resulting HTML of each request; exits non-zero if a request failed."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings  # noqa: E402
from app.deck_chat import DeckChatError, run_chat  # noqa: E402
from app.llm import BedrockLLM  # noqa: E402
from app.models import ChatMessage, Deck, Slide  # noqa: E402
from app.slides_html import sanitize_slide_html  # noqa: E402

NOW = datetime.now(timezone.utc)
SLIDES = [
    "<h1>Ταξινόμηση φυσαλίδας</h1><p>Διάλεξη 4 — Αλγόριθμοι και πολυπλοκότητα</p>",
    "<h2>Η ιδέα</h2><ul><li><p>Συγκρίνουμε γειτονικά στοιχεία</p></li><li><p>Ανταλάσουμε αν είναι σε λάθος σειρά</p></li>"
    "<li><p>Επαναλαμβάνουμε μέχρι να μην γίνει καμία ανταλαγή</p></li></ul>",
    "<h2>Παράδειγμα</h2><p>Πίνακας: 5, 1, 4, 2, 8</p><p>Μετά το πρώτο πέρασμα: 1, 4, 2, 5, 8</p>",
    "<h2>Ερωτήσεις</h2><p>Πότε σταματά ο αλγόριθμος;</p>",
]
REQUESTS = [
    ("Τι διαφορά έχει από την ταξινόμηση με εισαγωγή; Απάντησέ μου σύντομα.", None),
    ("Γράψε δύο διαφάνειες για την πολυπλοκότητα μετά το παράδειγμα και κάνε όλους τους τίτλους μπλε.", None),
    ("Διόρθωσε τα ορθογραφικά σε αυτή τη διαφάνεια και βάλε κουκκίδες στο παράδειγμα.", 1),
]


def main() -> int:
    settings = load_settings()
    llm = BedrockLLM(settings)
    deck = Deck(id="try0000001", created_at=NOW, updated_at=NOW, title="Ταξινόμηση φυσαλίδας", language="el",
                slides=[Slide(id=f"s{i + 1:07d}", html=h) for i, h in enumerate(SLIDES)])
    requests = [(sys.argv[1], None)] if len(sys.argv) > 1 else REQUESTS
    failures = 0
    for message, slide_index in requests:
        slide_id = deck.slides[slide_index].id if slide_index is not None else None
        print(f"\n=== {message}  (slide {slide_id})")
        started = time.monotonic()
        try:
            reply, slides, log = run_chat(llm, deck, "", message, slide_id=slide_id, selection=None)
        except DeckChatError as exc:
            failures += 1
            print(f"FAILED after {time.monotonic() - started:.1f}s: {exc}")
            continue
        print(f"{time.monotonic() - started:.1f}s  reply: {reply}")
        for e in log:
            print(f"  {e.op:13} {e.slide_id}  {e.title}")
        for s in slides:
            if s.html != next((o.html for o in deck.slides if o.id == s.id), None):
                clean = sanitize_slide_html(s.html) == s.html
                print(f"  [{s.id}] {'ok ' if clean else 'DIRTY '}{s.html}")
        deck.slides = slides
        deck.chat = deck.chat + [ChatMessage(role="user", content=message, at=NOW),
                                 ChatMessage(role="assistant", content=reply, edits=log, at=NOW)]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
