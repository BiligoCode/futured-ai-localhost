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
    "Export not found": "Το αρχείο εξαγωγής δεν βρέθηκε",
    "Please give the slides a title": "Δώστε έναν τίτλο στις διαφάνειες",
    # Assessments
    "Assessment not found": "Η αξιολόγηση δεν βρέθηκε",
    "Paper not found": "Το γραπτό δεν βρέθηκε",
    "Page not found": "Η σελίδα δεν βρέθηκε",
    "Please give the assessment a title": "Δώστε έναν τίτλο στην αξιολόγηση",
    "The grade scale must be 10, 20 or 100": "Η κλίμακα βαθμολογίας πρέπει να είναι 10, 20 ή 100",
    "Upload at most 10 files for the exam paper": "Ανεβάστε έως 10 αρχεία για το θέμα της εξέτασης",
    "The exam paper must be PDF, JPG or PNG files": "Το θέμα της εξέτασης πρέπει να είναι αρχεία PDF, JPG ή PNG",
    "Split every 1 to 40 pages": "Ο διαχωρισμός γίνεται ανά 1 έως 40 σελίδες",
    "Upload at most 120 files at a time": "Ανεβάστε έως 120 αρχεία τη φορά",
    "Already uploaded": "Έχει ήδη ανέβει",
    "The file is larger than 50 MB": "Το αρχείο είναι μεγαλύτερο από 50 MB",
    "Only PDF, JPG and PNG files can be graded": "Βαθμολογούνται μόνο αρχεία PDF, JPG και PNG",
    "Could not read the file": "Δεν ήταν δυνατή η ανάγνωση του αρχείου",
    "The PDF is password-protected": "Το PDF προστατεύεται με κωδικό",
    "The PDF has no pages": "Το PDF δεν έχει σελίδες",
    "This paper has more than 40 pages": "Το γραπτό έχει περισσότερες από 40 σελίδες",
    "This question has no result yet": "Αυτή η ερώτηση δεν έχει ακόμα αποτέλεσμα",
    "Only a paper that failed can be retried": "Μόνο ένα γραπτό που απέτυχε μπορεί να ξαναδοκιμαστεί",
    "Lara is already drafting the rubric": "Η Lara ετοιμάζει ήδη το κλειδί βαθμολόγησης",
    "Add the exam paper or wait until a paper has been read":
        "Προσθέστε το θέμα της εξέτασης ή περιμένετε να διαβαστεί ένα γραπτό",
    "The class analysis needs at least two graded papers":
        "Η ανάλυση της τάξης χρειάζεται τουλάχιστον δύο βαθμολογημένα γραπτά",
    "Add at least one question before grading": "Προσθέστε τουλάχιστον μία ερώτηση πριν από τη βαθμολόγηση",
    "Interrupted by server restart": "Διακόπηκε από επανεκκίνηση του διακομιστή",
}

PREFIXES = {
    "The AI model request failed: ": "Το αίτημα προς το μοντέλο AI απέτυχε: ",
    "Could not generate a valid storyboard: ": "Δεν ήταν δυνατή η δημιουργία έγκυρου σεναρίου: ",
    "Could not work out which part of the video to change: ":
        "Δεν ήταν δυνατό να βρεθεί ποιο σημείο του βίντεο να αλλάξει: ",
    "ElevenLabs request failed": "Το αίτημα προς το ElevenLabs απέτυχε",
    "ElevenLabs returned an unexpected response: ": "Το ElevenLabs επέστρεψε απρόσμενη απάντηση: ",
    "Export failed: ": "Η εξαγωγή απέτυχε: ",
    "Could not take a still from the animation: ": "Δεν ήταν δυνατή η λήψη καρέ από την κινούμενη εικόνα: ",
    # Assessments
    "Two questions have the same label: ": "Δύο ερωτήσεις έχουν την ίδια ετικέτα: ",
    "Choose whether the answer is true or false for question: ":
        "Επιλέξτε αν η απάντηση είναι «Σωστό» ή «Λάθος» στην ερώτηση: ",
    "Give the correct option for question: ": "Δώστε τη σωστή επιλογή για την ερώτηση: ",
    "Give the correct number for question: ": "Δώστε τον σωστό αριθμό για την ερώτηση: ",
    "Give the expected answer for question: ": "Δώστε την αναμενόμενη απάντηση για την ερώτηση: ",
    "The criteria do not add up to the points of question: ": "Τα κριτήρια δεν αθροίζουν στις μονάδες της ερώτησης: ",
    "Reading the paper failed: ": "Η ανάγνωση του γραπτού απέτυχε: ",
    "Grading failed: ": "Η βαθμολόγηση απέτυχε: ",
    "Could not draft a rubric: ": "Δεν ήταν δυνατή η σύνταξη κλειδιού βαθμολόγησης: ",
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
