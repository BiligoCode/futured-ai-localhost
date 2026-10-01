"""Server messages in the dashboard's language. The dashboard sends `X-Lara-Lang: el|en`; other clients get English.

Messages are written in English at the source and translated here, exactly or by prefix (the technical detail
after a prefix, such as a model error, is kept as is)."""
from starlette.requests import Request

LANG_HEADER = "x-lara-lang"

EXACT = {
    "Project not found": "Το έργο δεν βρέθηκε",
    "Scene not found": "Το τμήμα δεν βρέθηκε",
    "Cancelled": "Ακυρώθηκε",
    "Scene is already being processed": "Αυτό το τμήμα επεξεργάζεται ήδη",
    "Scene has not been rendered yet": "Αυτό το τμήμα δεν έχει δημιουργηθεί ακόμα",
    "Storyboard can only be edited before rendering starts":
        "Το σενάριο αλλάζει μόνο πριν ξεκινήσει η δημιουργία του βίντεο",
    "Wait until the video is ready before asking for changes":
        "Περιμένετε να ετοιμαστεί το βίντεο πριν ζητήσετε αλλαγές",
    "That part of the video is still being changed. Try again when it is done.":
        "Αυτό το σημείο του βίντεο αλλάζει ακόμα. Δοκιμάστε ξανά όταν τελειώσει.",
    "Wait until the video is ready before adding narration":
        "Περιμένετε να ετοιμαστεί το βίντεο πριν προσθέσετε αφήγηση",
    "Narration is already being generated": "Η αφήγηση δημιουργείται ήδη",
    "Invalid pauses in the recording": "Μη έγκυρες παύσεις στην ηχογράφηση",
    "Could not read the recording": "Η ηχογράφηση δεν ήταν αναγνώσιμη",
    "This scene has no narration audio yet": "Αυτό το τμήμα δεν έχει ακόμα αφήγηση",
    "The video changed while you were recording. Please record again.":
        "Το βίντεο άλλαξε όσο ηχογραφούσατε. Ηχογραφήστε ξανά.",
    "Unknown starting point for the recording": "Άγνωστο σημείο έναρξης της ηχογράφησης",
    "The recording is empty": "Η ηχογράφηση είναι κενή",
    "The animation is not finished yet": "Η κινούμενη εικόνα δεν έχει ολοκληρωθεί ακόμα",
    "The video could not be put together": "Δεν ήταν δυνατή η σύνθεση του βίντεο",
    "This project has no narrated video yet": "Αυτό το έργο δεν έχει ακόμα βίντεο με αφήγηση",
    "The video is not ready yet": "Το βίντεο δεν είναι ακόμα έτοιμο",
    "No readable text found in the uploaded material": "Δεν βρέθηκε αναγνώσιμο κείμενο στο υλικό",
    "Could not read the uploaded PDF": "Δεν ήταν δυνατή η ανάγνωση του PDF",
    "AI voice is not configured: set ELEVENLABS_API_KEY in .env":
        "Η φωνή AI δεν έχει ρυθμιστεί: ορίστε ELEVENLABS_API_KEY στο .env",
    # Slides
    "Slides not found": "Οι διαφάνειες δεν βρέθηκαν",
    "The slides were changed elsewhere": "Οι διαφάνειες άλλαξαν από αλλού",
    "The AI reply could not be applied. Please try again.":
        "Η απάντηση του AI δεν μπόρεσε να εφαρμοστεί. Δοκιμάστε ξανά.",
    "The animation is not ready yet": "Η κινούμενη εικόνα δεν είναι ακόμα έτοιμη",
    "Slide is too long": "Η διαφάνεια είναι πολύ μεγάλη",
    "This slide does not exist": "Αυτή η διαφάνεια δεν υπάρχει",
    "Poster not found": "Η εικόνα δεν βρέθηκε",
}

PREFIXES = {
    "The AI model request failed: ": "Το αίτημα προς το μοντέλο AI απέτυχε: ",
    "Could not generate a valid storyboard: ": "Δεν ήταν δυνατή η δημιουργία έγκυρου σεναρίου: ",
    "Could not work out which part of the video to change: ":
        "Δεν ήταν δυνατό να βρεθεί ποιο σημείο του βίντεο να αλλάξει: ",
    "ElevenLabs request failed": "Το αίτημα προς το ElevenLabs απέτυχε",
    "ElevenLabs returned an unexpected response: ": "Το ElevenLabs επέστρεψε απρόσμενη απάντηση: ",
    "Export failed: ": "Η εξαγωγή απέτυχε: ",
}


def request_language(request: Request) -> str:
    return "el" if request.headers.get(LANG_HEADER, "").lower().startswith("el") else "en"


def translate(message: str, language: str) -> str:
    if language != "el" or not isinstance(message, str):
        return message
    if message in EXACT:
        return EXACT[message]
    for prefix, greek in PREFIXES.items():
        if message.startswith(prefix):
            return greek + message[len(prefix):]
    return message
