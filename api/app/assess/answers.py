"""Reading a student's final answer the way a Greek or English professor would (design §6.4).

Everything here is deterministic: the model only reports what the student wrote, these functions decide what it
means (true or false, which options, which number) so the comparison with the key is exact."""
import math
import re
import unicodedata

GREEK_OPTIONS = ["α", "β", "γ", "δ", "ε", "στ", "ζ", "η", "θ", "ι"]
LATIN_OPTIONS = list("abcdefghij")

_STRUCK = re.compile(r"~~.*?~~", re.DOTALL)
_WRAPPER = re.compile(r"\(?\s*(?:circled|ticked|underlined|marked|checked|selected|κυκλωμ\w*|επιλεγμ\w*|σημειωμ\w*)\s*[:：]\s*",
                      re.IGNORECASE)
_SPACES = re.compile(r"\s+")
_SUPERSCRIPTS = str.maketrans({"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7",
                               "⁸": "8", "⁹": "9", "⁻": "-", "⁺": "+"})


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def remove_struck(text: str) -> str:
    """Drop what the student crossed out (transcribed as ~~…~~)."""
    return _STRUCK.sub(" ", text or "")


def normalize_text(text: str | None) -> str:
    """Case-, accent- and spacing-insensitive form used for every comparison. Final sigma becomes σ."""
    text = unicodedata.normalize("NFKC", remove_struck(text or ""))
    text = strip_accents(text.casefold()).replace("ς", "σ")
    return _SPACES.sub(" ", text).strip()


def _unwrap(text: str) -> str:
    """'(circled: β)' → 'β)'; the reader marks circled or ticked options this way."""
    return _WRAPPER.sub(" ", text)


def is_blank(final: str | None) -> bool:
    text = normalize_text(final)
    return not re.sub(r"[\W_]+", "", text) or text in {"null", "none", "-", "—", "n/a", "κενο", "καμια", "δεν απαντησε"}


# --- True / false -----------------------------------------------------------------------------------------------

_TRUE = {"σ", "σωστο", "σωστη", "σωστοσ", "σωστα", "α", "αληθεσ", "αληθησ", "αληθεια", "αληθινο", "ναι", "true", "t",
         "yes", "y", "correct", "right", "✓", "✔", "√"}
_FALSE = {"λ", "λαθοσ", "λαθοσ", "λανθασμενο", "λαθο", "ψ", "ψευδεσ", "ψευδησ", "ψεμα", "οχι", "false", "f", "no", "n",
          "wrong", "incorrect", "✗", "✘", "×"}
_TF_TOKEN = re.compile(r"[\w✓✔√✗✘×]+")
_NEGATIONS = {"not", "δεν", "μη", "μην", "οχι"}


def parse_true_false(final: str | None) -> bool | None:
    """True, False, or None when nothing (or something contradictory) was answered. The first true/false word wins,
    so "Λάθος, το σωστό είναι …" is False; "not true" is False."""
    tokens = _TF_TOKEN.findall(normalize_text(_unwrap(final or "")))
    for i, tok in enumerate(tokens):
        value = True if tok in _TRUE else False if tok in _FALSE else None
        if value is None:
            continue
        if i > 0 and tokens[i - 1] in _NEGATIONS and tok not in _NEGATIONS:
            return not value
        return value
    return None


# --- Multiple choice --------------------------------------------------------------------------------------------

_OPTION_LABEL = re.compile(r"^\s*\(?\s*(στ|[α-θι]|[a-j]|\d{1,2})\s*[\).:΄'’-]\s*", re.IGNORECASE)
_LABELLED = re.compile(r"(?<![\w])\(?(στ|[α-θι]|[a-j]|\d{1,2})\s*[\)΄'’]")
_TOKEN = re.compile(r"[\w]+")


def _ordinal(token: str) -> int | None:
    token = strip_accents(token.casefold())
    if token in GREEK_OPTIONS:
        return GREEK_OPTIONS.index(token)
    if token in LATIN_OPTIONS:
        return LATIN_OPTIONS.index(token)
    if token.isdigit() and 1 <= int(token) <= 12:
        return int(token) - 1
    return None


def option_text(option: str) -> str:
    """The text of an option without its label: 'β) O(n log n)' → 'O(n log n)'."""
    return _OPTION_LABEL.sub("", option, count=1).strip()


def compact(text: str) -> str:
    """Only letters and digits of the normalised text: "O(n log n)" and "o(nlogn)" are the same."""
    return re.sub(r"[\W_]+", "", normalize_text(text.translate(_SUPERSCRIPTS)))


def option_letter(index: int, like: str = "") -> str:
    """The label to show for option `index`, in the script of `like` (Greek if the key is Greek)."""
    greek = bool(re.search(r"[α-ωΑ-Ω]", like))
    letters = GREEK_OPTIONS if greek else LATIN_OPTIONS
    return letters[index] if index < len(letters) else str(index + 1)


def parse_choices(final: str | None, options: list[str] | None = None, *, n_options: int | None = None) -> frozenset[int] | None:
    """The set of option indexes the student chose (0-based), or None if none can be found.

    Labels are matched in Greek (α β γ δ ε στ ζ η θ), Latin (a–j) or digits; an option's text written out in full
    counts too. Letters beyond the number of options are ignored (so the Greek article "η" in a sentence is not
    option 8 of a four-option question). Digits count only when the options themselves are numbered."""
    options = options or []
    limit = n_options or len(options) or 8
    raw = strip_accents(_unwrap(remove_struck(final or "")).casefold())
    numbered = bool(options) and all(re.match(r"^\s*\(?\d", o) for o in options)

    def chosen(tokens: list[str]) -> frozenset[int] | None:
        found = frozenset(i for t in tokens if (numbered or not t.isdigit())
                          for i in [_ordinal(t)] if i is not None and i < limit)
        return found or None

    if found := chosen([m.group(1) for m in _LABELLED.finditer(raw)]):
        return found
    tokens = [t for t in _TOKEN.findall(raw) if len(t) <= 2]
    if found := chosen(tokens):
        return found
    # A lone letter is an answer even beyond the listed options (the rubric may list only some of them).
    words = _TOKEN.findall(raw)
    if len(words) == 1 and len(words[0]) <= 2 and (i := _ordinal(words[0])) is not None and (numbered or not words[0].isdigit()):
        return frozenset({i})
    # The option written out in full ("O(n log n)") instead of its letter.
    text = compact(raw)
    if text and options:
        matches = [i for i, o in enumerate(options)
                   if (c := compact(option_text(o))) and (c == text or (len(c) >= 4 and c in text))]
        if matches:
            return frozenset(matches)
    return None


# --- Numbers ----------------------------------------------------------------------------------------------------

_NUMBER = re.compile(
    r"""(?P<sign>[-+−])?\s*
        (?P<int>\d{1,3}(?:[ .,'’]\d{3})+(?!\d)|\d+)
        (?:(?P<dec_sep>[.,])(?P<dec>\d+))?
        (?:\s*/\s*(?P<den>\d+(?:[.,]\d+)?))?
        (?:\s*(?:e|E|[x×*·]\s*10\s*\^?\s*)\(?\s*(?P<exp>[-+−]?\d+)\s*\)?)?
        (?P<pct>\s*%)?""",
    re.VERBOSE,
)


def _plain(s: str) -> float:
    return float(s.replace(",", "."))


def _int_readings(group: str) -> list[float]:
    """'1.000' could be one thousand (Greek grouping) or 1.0 (decimal point): both readings, most likely first."""
    if re.fullmatch(r"\d+", group):
        return [float(group)]
    seps = set(re.findall(r"[ .,'’]", group))
    digits = re.sub(r"\D", "", group)
    if len(seps) == 1 and (sep := next(iter(seps))) in ".,":
        parts = group.split(sep)
        if len(parts) == 2:
            if parts[0] == "0":
                return [float("0." + parts[1])]
            return [float(digits), float(parts[0] + "." + parts[1])]
    return [float(digits)]


def parse_numbers(final: str | None) -> list[float]:
    """Readings of the student's final number (the last number written), most likely first; [] if there is none.

    Handles decimal commas (0,5), thousands separators (1.000 / 1,000 / 12 500), fractions (7/1000), percentages,
    scientific notation (7e-3, 7·10^-3, 7×10⁻³) and units after the number. A number like 1.000 is genuinely
    ambiguous between Greek and English conventions and returns both readings."""
    text = remove_struck(final or "").translate(_SUPERSCRIPTS).replace("−", "-").replace(" ", " ")
    text = re.sub(r"(?<=\d)\s*[·x×*]\s*10\s*\^?\s*(?=[-+(]?\d)", "×10^", text)
    text = re.sub(r"(?<![\d.,×])10\s*\^\s*\(?\s*([-+]?\d+)\s*\)?", r"1×10^\1", text)
    matches = list(_NUMBER.finditer(text))
    if not matches:
        return []
    m = matches[-1]
    sign = -1.0 if m.group("sign") in ("-", "−") else 1.0
    if m.group("dec") is not None:
        # A decimal part after a (possibly grouped) integer: the last separator is the decimal one.
        values = [float(re.sub(r"\D", "", m.group("int")) + "." + m.group("dec"))]
    else:
        values = _int_readings(m.group("int"))
    if m.group("den"):
        den = _plain(m.group("den"))
        values = [v / den for v in values if den] or values
    if m.group("exp"):
        exp = int(m.group("exp").replace("−", "-"))
        values = [v * 10 ** exp for v in values]
    values = [sign * v for v in values]
    if m.group("pct"):
        values = values + [v / 100 for v in values]
    out: list[float] = []
    for v in values:
        if math.isfinite(v) and not any(math.isclose(v, o, rel_tol=1e-12, abs_tol=0) for o in out):
            out.append(v)
    return out


def numbers_match(candidates: list[float], key: float, tolerance: float) -> bool:
    allowed = max(tolerance, 1e-9 * max(1.0, abs(key)))
    return any(abs(c - key) <= allowed for c in candidates)


# --- Short answers ----------------------------------------------------------------------------------------------

def key_alternatives(key: str) -> list[str]:
    return [k.strip() for k in (key or "").split("|") if k.strip()]


def short_matches(final: str | None, key: str) -> bool:
    """Exact match after normalisation (case, accents, spacing, punctuation, superscripts) with any alternative."""
    answer = compact(final or "")
    return bool(answer) and any(answer == compact(k) for k in key_alternatives(key))
