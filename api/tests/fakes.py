import json


class ScriptedLLM:
    """Returns scripted responses in order; raises items that are exceptions."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, list[dict]]] = []

    def __call__(self, system: str, messages: list[dict]) -> str:
        self.calls.append((system, [dict(m) for m in messages]))
        if not self.responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeRenderer:
    """Async renderer returning scripted RenderResults; repeats the last one when exhausted."""

    def __init__(self, results):
        self.results = list(results)
        self.calls: list[tuple] = []

    async def __call__(self, code_path, output_path):
        self.calls.append((code_path, output_path))
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if result.ok:
            output_path.write_bytes(b"fake-mp4")
        return result


class FakeTTS:
    name = "fake"

    def __init__(self, audio: bytes, fail: bool = False):
        self.audio = audio
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def cache_key(self, text: str, language: str = "") -> str:
        return f"fake-{abs(hash((text, language)))}"

    def synthesize(self, text: str, language: str) -> bytes:
        from app.tts import TTSError

        self.calls.append((text, language))
        if self.fail:
            raise TTSError("ElevenLabs request failed (401)")
        return self.audio


VALID_CODE = """from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("Γεια", font="DejaVu Sans")))
        self.wait(1)
"""

INVALID_SYNTAX_CODE = "from manim import *\nclass GeneratedScene(Scene:\n    pass\n"


STORYBOARD_JSON = json.dumps({
    "title": "Κάθοδος κλίσης",
    "scenes": [
        {"title": "Το πρόβλημα", "visual": "Μια καμπύλη κόστους με ένα σημείο",
         "narration": "Θέλουμε να βρούμε το ελάχιστο της συνάρτησης κόστους."},
        {"title": "Η κλίση", "visual": "Βέλος εφαπτομένης στο σημείο",
         "narration": "Η κλίση μας δείχνει προς τα πού ανεβαίνει η συνάρτηση."},
        {"title": "Το βήμα", "visual": "Το σημείο μετακινείται αντίθετα από την κλίση",
         "narration": "Κάνουμε ένα μικρό βήμα αντίθετα από την κλίση."},
        {"title": "Σύγκλιση", "visual": "Επαναλαμβανόμενα βήματα μέχρι το ελάχιστο",
         "narration": "Επαναλαμβάνοντας, φτάνουμε κοντά στο ελάχιστο."},
    ],
}, ensure_ascii=False)


class FnLLM:
    """A text model answered by a function of (system, messages); records the calls."""

    def __init__(self, fn):
        self.fn = fn
        self.calls: list[tuple[str, list[dict]]] = []

    def __call__(self, system: str, messages: list[dict]) -> str:
        self.calls.append((system, [dict(m) for m in messages]))
        reply = self.fn(system, messages)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FnVision:
    """A vision model answered by a function of (system, prompt, images); records the calls."""

    def __init__(self, fn):
        self.fn = fn
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, system: str, prompt: str, images: list[bytes]) -> str:
        self.calls.append((system, prompt, len(images)))
        reply = self.fn(system, prompt, images)
        if isinstance(reply, Exception):
            raise reply
        return reply
