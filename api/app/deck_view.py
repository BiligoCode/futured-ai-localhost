"""What the dashboard and the deck editor see: a deck plus the animations around it, computed from the projects."""
from app.models import AnimationRef, Deck, DeckSummary, DeckView, Project


def _ref(project: Project, embedded: bool) -> AnimationRef:
    if project.stage == "storyboard":
        status, cut = "draft", None
    elif project.preview.version == 0:
        status, cut = "creating", None
    else:
        status, cut = "ready", "final" if project.final.version > 0 else "preview"
    chosen = project.final if cut == "final" else project.preview
    return AnimationRef(project_id=project.id, title=project.title, status=status, cut=cut,
                        version=chosen.version if cut else 0, signature=chosen.signature if cut else "",
                        duration=chosen.duration if cut else 0.0,
                        embedded=embedded)


def animation_refs(deck: Deck, projects: list[Project]) -> list[AnimationRef]:
    """Projects made from the deck and projects embedded in a slide, newest first; embedded projects that
    were deleted are kept as `missing` so the editor can show a placeholder."""
    embedded = {s.video for s in deck.slides if s.video}
    by_id = {p.id: p for p in projects}
    linked = sorted((p for p in projects if p.deck_id == deck.id or p.id in embedded),
                    key=lambda p: p.created_at, reverse=True)
    refs = [_ref(p, p.id in embedded) for p in linked]
    refs += [AnimationRef(project_id=pid, title="", status="missing", cut=None, version=0, duration=0.0,
                          embedded=True) for pid in sorted(embedded) if pid not in by_id]
    return refs


def build_view(deck: Deck, projects: list[Project]) -> DeckView:
    return DeckView(**deck.model_dump(), animations=animation_refs(deck, projects))


def summarize(deck: Deck, projects: list[Project]) -> DeckSummary:
    return DeckSummary(
        id=deck.id, created_at=deck.created_at, updated_at=deck.updated_at, title=deck.title,
        language=deck.language, slide_count=len(deck.slides),
        animation_count=sum(1 for p in projects if p.deck_id == deck.id),
        first_slide_html=deck.slides[0].html if deck.slides else "",
    )
