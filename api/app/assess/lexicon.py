"""Word lists for the AI-likeness signals and the forensics (design §8, §9; research notes R 10, 15, 18).

All patterns run on `answers.normalize_text` output: lower case, Greek accents stripped, final ς written σ.
The English style words follow Kobak et al. (2024) plus well-known LLM-isms; the Greek list was written for Lara and
deliberately leaves out words that are simply formal Greek ("επιπλέον", "ωστόσο", "αποτελεί", "πλαίσιο"),
because flagging ordinary academic Greek would accuse honest students."""
import re

_W = r"(?<![\w])"   # start of a word
_E = r"(?![\w])"    # end of a word


def _words(*stems: str) -> re.Pattern:
    return re.compile(_W + "(?:" + "|".join(stems) + ")" + _E)


# Style words whose frequency jumped with LLMs. Each hit counts once.
AI_WORDS_EN = _words(
    r"delv(?:e|es|ed|ing)", r"underscor(?:e|es|ed|ing)", r"showcas(?:e|es|ed|ing)", r"pivotal",
    r"intricat(?:e|ely|acies|acy)", r"meticulous(?:ly)?", r"tapestr(?:y|ies)", r"realms?", r"multifaceted",
    r"nuanced", r"comprehensive(?:ly)?", r"crucial(?:ly)?", r"notably", r"leverag(?:e|es|ed|ing)",
    r"foster(?:s|ed|ing)?", r"bolster(?:s|ed|ing)?", r"seamless(?:ly)?", r"streamlin(?:e|es|ed|ing)",
    r"holistic(?:ally)?", r"paramount", r"embark(?:s|ed|ing)?", r"harness(?:es|ed|ing)?", r"unveil(?:s|ed|ing)?",
    r"intriguing", r"commendable", r"noteworthy", r"invaluable", r"vibrant", r"testament", r"endeavou?rs?",
    r"interplay", r"synerg(?:y|ies|istic)", r"facilitat(?:e|es|ed|ing)", r"utili[sz](?:e|es|ed|ing)",
    r"encompass(?:es|ed|ing)?", r"garner(?:s|ed|ing)?", r"myriad", r"plethora", r"quintessential",
    r"resonat(?:e|es|ed|ing)", r"enhanc(?:e|es|ed|ing|ement)", r"insightful", r"elevat(?:e|es|ed|ing)",
    r"transformative", r"groundbreaking", r"game-?changer", r"cutting-edge", r"ever-evolving",
)

AI_WORDS_EL = _words(
    r"εμβαθυν\w*", r"υπογραμμιζ\w*", r"αναδεικνυ\w*", r"πολυδιαστατ\w*", r"ολιστικ\w*", r"ακρογωνιαι\w*",
    r"αδιαμφισβητητ\w*", r"πληθωρα", r"αξιοποιωντασ", r"απροσκοπτ\w*", r"μεταμορφωτικ\w*",
    r"αξιοσημειωτ\w*", r"καινοτομ\w* προσεγγισ\w*", r"ευρυ φασμα", r"καιριασ σημασιασ", r"αναποσπαστο (?:κομματι|μεροσ)",
    r"διαδραματιζ\w* (?:\w+ )?(?:καθοριστικ|κρισιμ|καιρι|κεντρικ|πρωταγωνιστικ|ουσιαστικ)\w* ρολο",
    r"δυναμικ\w* τοπι\w*", r"συνεχωσ εξελισσομεν\w*", r"σημερινο ψηφιακο κοσμο",
)

# Formulaic moves: summaries, signposting, "not only … but also".
FORMULAIC = re.compile("|".join([
    _W + r"it(?: is|'s) (?:important|worth|crucial) (?:to note|noting|to remember|to consider)",
    _W + r"it should be noted", _W + r"in conclusion", _W + r"in summary", _W + r"to sum up", _W + r"to summari[sz]e",
    _W + r"overall,", _W + r"not only\b.{1,80}?\bbut also", _W + r"plays? an? (?:crucial|pivotal|key|vital|significant|central) role",
    _W + r"a testament to", _W + r"in today'?s (?:fast-paced|digital|modern|ever-evolving|rapidly)", _W + r"in the realm of",
    _W + r"(?:delve|dive) into", _W + r"navigat\w* the complexit", _W + r"first and foremost", _W + r"at its core",
    _W + r"let'?s (?:explore|dive|break|delve|unpack)", _W + r"key takeaways?", _W + r"firstly,", _W + r"secondly,",
    _W + r"lastly,", _W + r"a wide (?:range|array|variety) of",
    _W + r"συνοψιζοντασ", _W + r"συμπερασματικα", _W + r"εν κατακλειδι", _W + r"επιπροσθετωσ",
    _W + r"ειναι σημαντικο να (?:σημειωθει|τονιστει|αναφερθει|επισημανθει|κατανοησουμε)",
    _W + r"αξιζει να (?:σημειωθει|αναφερθει|τονιστει|επισημανθει)", _W + r"οχι μονο\b.{1,80}?\bαλλα και",
    _W + r"πρωτον,", _W + r"δευτερον,", _W + r"ασ (?:εξετασουμε|δουμε|εμβαθυνουμε|αναλυσουμε|ξεκινησουμε)",
    _W + r"με απλα λογια", _W + r"στον πυρηνα του",
]))

# Leftovers of a chat assistant's reply: near-proof that text was pasted from one (R 15).
CHAT_ARTIFACTS = re.compile("|".join([
    r"as an ai(?: language model)?", r"as a (?:large )?language model", r"i(?:'m| am) (?:just )?an ai",
    r"i hope (?:this|that) helps", r"let me know if (?:you|there)", r"feel free to (?:ask|reach out|let me know)",
    r"(?:sure|certainly|of course|absolutely)[!,.] here(?:'s| is| are)",
    r"here(?:'s| is) (?:a |an |the )?(?:revised|rewritten|polished|improved|concise|detailed|refined) (?:version|answer|text|draft)",
    r"as of my (?:last|knowledge) (?:update|cutoff)", r"my knowledge cutoff", r"i (?:can't|cannot) browse",
    r"regenerate response", r"would you like me to",
    r"ωσ (?:ενα )?(?:μοντελο|γλωσσικο μοντελο|μοντελο τεχνητησ νοημοσυνησ|τεχνητη νοημοσυνη)",
    r"ελπιζω (?:αυτο |αυτα )?να (?:σε |σασ )?(?:βοηθ|φαν)\w*", r"ενημερωσ(?:ε|τε) με αν",
    r"(?:φυσικα|βεβαιωσ|σιγουρα)[!,.] (?:ορισ(?:τε)?|ακολουθει|ιδου)",
    r"ορισ(?:τε)? (?:μια|ενα|η) (?:αναθεωρημενη|βελτιωμενη|πιο συντομη|πιο αναλυτικη|διορθωμενη)",
    r"θα (?:ηθελεσ|θελατε) να (?:σου|σασ) ",
]))

# Citation markers that ChatGPT's search and file tools leave behind when their answer is copied (R 15).
CITATION_ARTIFACTS = re.compile(
    r"contentreference\[oaicite|oaicite:\d|\bturn\d+(?:search|news|view|fetch|file)\d+|utm_source=chatgpt\.com"
    r"|utm_source=openai|【\d+(?::\d+)?†|citeturn\d", re.IGNORECASE)

MARKDOWN = re.compile(r"\*\*[^*\n]{2,80}\*\*|^\s{0,3}#{1,4} \S|```|^\s*[-*] \*\*", re.MULTILINE)

# Text that talks to an AI grader or tries to steer it (R 18).
ADDRESSES_GRADER = re.compile("|".join([
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier|preceding) (?:instructions|prompts?|rules)",
    r"disregard (?:all |any )?(?:the )?(?:previous|prior|above) (?:instructions|prompts?)",
    r"(?:give|award|assign) (?:this |the |me |him |her )?(?:student |paper |answer |essay |submission |exam )?"
    r"(?:full|maximum|max|top|perfect|the highest|highest) (?:marks?|score|points|grade)",
    r"if you are (?:an? )?(?:ai|llm|language model|chatgpt|grader|grading (?:system|model|assistant))",
    r"(?:as|you are) (?:the|an|a) (?:ai |automated )?grader", r"(?:grade|mark|score) (?:this|it) as (?:correct|full|perfect|10|100)",
    r"system prompt", r"new instructions:",
    r"αγνοησ(?:ε|τε) (?:ολεσ |τισ )?(?:προηγουμενεσ |παραπανω |αρχικεσ )?οδηγιεσ",
    r"(?:βαλε|βαλτε|δωσε|δωστε) (?:μου |στον φοιτητη |στη φοιτητρια |στην εργασια |σε αυτη την εργασια )?"
    r"(?:αριστα|αριστο|τον μεγιστο βαθμο|μεγιστο βαθμο|πληρη βαθμο|ολεσ τισ μοναδεσ|10/10|δεκα)",
    r"αν εισαι (?:ενα |μια )?(?:ai|μοντελο|γλωσσικο μοντελο|τεχνητη νοημοσυνη|chatgpt|βαθμολογητ\w*)",
    r"(?:βαθμολογησ(?:ε|τε)) (?:το|την|αυτο|αυτη) ωσ (?:σωστο|σωστη|αριστο|αριστη)",
]))

# Characters that typing does not produce (R 14). U+00A0 is left out: Word inserts it in ordinary Greek text.
ZERO_WIDTH = {"​": "ZERO WIDTH SPACE", "‌": "ZERO WIDTH NON-JOINER", "‍": "ZERO WIDTH JOINER",
              "⁠": "WORD JOINER", "﻿": "ZERO WIDTH NO-BREAK SPACE", "­": "SOFT HYPHEN",
              "‪": "LEFT-TO-RIGHT EMBEDDING", "‫": "RIGHT-TO-LEFT EMBEDDING", "‬": "POP DIRECTIONAL FORMATTING",
              "‭": "LEFT-TO-RIGHT OVERRIDE", "‮": "RIGHT-TO-LEFT OVERRIDE", "⁦": "LEFT-TO-RIGHT ISOLATE",
              "⁧": "RIGHT-TO-LEFT ISOLATE", "⁩": "POP DIRECTIONAL ISOLATE"}
NARROW_NBSP = " "
TAG_CHARS = re.compile("[\U000E0000-\U000E007F]")
EM_DASH = "—"


def invisible_counts(text: str) -> dict[str, int]:
    """Count invisible or formatting characters by name (soft hyphens only when they sit inside a word)."""
    counts: dict[str, int] = {}
    for ch, name in ZERO_WIDTH.items():
        n = text.count(ch)
        if ch == "﻿" and text.startswith(ch):
            n -= 1  # a byte-order mark at the very start is harmless
        if n > 0:
            counts[name] = n
    if (n := text.count(NARROW_NBSP)) > 0:
        counts["NARROW NO-BREAK SPACE"] = n
    if (n := len(TAG_CHARS.findall(text))) > 0:
        counts["TAG CHARACTERS"] = n
    return counts


_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_LATIN = re.compile(r"[A-Za-z]")
_LOOKALIKE_GREEK = set("ΑΒΕΖΗΙΚΜΝΟΡΤΥΧαοριυνκ")
_WORD = re.compile(r"[^\W\d_]{4,}")


def mixed_script_words(text: str, limit: int = 10) -> list[str]:
    """Words that mix Latin with Cyrillic, or Latin with look-alike Greek letters — how students defeat plagiarism
    checkers ("Αlgorithm" with a Greek Alpha). Greek words with a Latin symbol inside are not counted."""
    found: list[str] = []
    for word in _WORD.findall(text):
        latin = len(_LATIN.findall(word))
        if not latin:
            continue
        cyr = len(_CYRILLIC.findall(word))
        greek_chars = _GREEK.findall(word)
        lookalike = greek_chars and all(c in _LOOKALIKE_GREEK for c in greek_chars) and len(greek_chars) < latin
        if (cyr and latin) or lookalike:
            if word not in found:
                found.append(word)
            if len(found) >= limit:
                break
    return found
