"""Captions for AI-narrated scenes: timed cues from the TTS character alignment, rendered as an ASS file that
ffmpeg burns into the bottom strip of the video (which the animations keep free)."""
from dataclasses import asdict, dataclass

LINE_CHARS = 42      # per caption line
MAX_LINES = 2
MAX_CUE_S = 6.0
SENTENCE_END = (".", "!", "?", ";", ":", "…")  # ";" is the Greek question mark

# 1280x720 canvas; two lines of 34 px text in an opaque box fit inside the reserved bottom strip (~117 px).
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Caption,DejaVu Sans,34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,0,0,0,0,100,100,0,0,3,6,0,2,80,80,22,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class _Word:
    text: str
    start: float
    end: float


def _words_from_alignment(alignment: dict) -> list[_Word]:
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words: list[_Word] = []
    current: _Word | None = None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            current = None
            continue
        if current is None:
            current = _Word(ch, float(s), float(e))
            words.append(current)
        else:
            current.text += ch
            current.end = float(e)
    return words


def _words_from_text(text: str, duration: float) -> list[_Word]:
    """No timing from the voice: spread the words over the audio in proportion to their length."""
    tokens = text.split()
    total = sum(len(t) + 1 for t in tokens) or 1
    words, t = [], 0.0
    for token in tokens:
        span = duration * (len(token) + 1) / total
        words.append(_Word(token, t, t + span))
        t += span
    return words


def _wrap(words: list[str]) -> str:
    lines, line = [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > LINE_CHARS:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    lines.append(line)
    return "\n".join(lines)


def _group(words: list[_Word]) -> list[Cue]:
    cues: list[Cue] = []
    group: list[_Word] = []

    def flush() -> None:
        if group:
            cues.append(Cue(start=round(group[0].start, 3), end=round(group[-1].end, 3),
                            text=_wrap([w.text for w in group])))
            group.clear()

    for word in words:
        candidate = [w.text for w in group] + [word.text]
        too_long = len(_wrap(candidate).split("\n")) > MAX_LINES or (group and word.end - group[0].start > MAX_CUE_S)
        if group and too_long:
            flush()
        group.append(word)
        if word.text.endswith(SENTENCE_END):
            flush()
    flush()
    # Keep each cue on screen until the next one starts (no flicker between words).
    for a, b in zip(cues, cues[1:]):
        a.end = max(a.end, min(b.start, a.end + 1.0))
    return cues


def cues_from_alignment(alignment: dict) -> list[Cue]:
    return _group(_words_from_alignment(alignment))


def cues_from_text(text: str, duration: float) -> list[Cue]:
    return _group(_words_from_text(text, duration))


def cues_to_json(cues: list[Cue]) -> list[dict]:
    return [asdict(c) for c in cues]


def cues_from_json(data: list[dict]) -> list[Cue]:
    return [Cue(**c) for c in data]


def _ass_time(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def to_ass(cues: list[Cue]) -> str:
    lines = [ASS_HEADER]
    for c in cues:
        text = c.text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Caption,,0,0,0,,{text}\n")
    return "".join(lines)
