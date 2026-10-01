import json
import re
from typing import Any

_FENCE = re.compile(r"```([\w+-]*)[ \t]*\n(.*?)```", re.DOTALL)


def _fences(text: str) -> list[tuple[str, str]]:
    return [(m.group(1).lower(), m.group(2)) for m in _FENCE.finditer(text)]


def extract_json(text: str) -> Any:
    candidates = [body for lang, body in _fences(text) if lang in ("json", "")] + [text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        for i, ch in enumerate(candidate):
            if ch in "{[":
                try:
                    value, _ = decoder.raw_decode(candidate, i)
                    return value
                except json.JSONDecodeError:
                    continue
    raise ValueError("No JSON object found in model reply")


def extract_code_block(text: str) -> str:
    fences = _fences(text)
    for lang, body in fences:
        if lang in ("python", "py"):
            return body.strip()
    if fences:
        return fences[0][1].strip()
    return text.strip()
