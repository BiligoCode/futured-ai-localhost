import asyncio
import re
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from app.deck_chat import DeckChatError, run_chat
from app.deck_store import new_slide_id
from app.deck_view import build_view, summarize
from app.ingest import EmptyMaterialError, build_material
from app.models import (ChatMessage, Deck, DeckChatRequest, DeckChatResult, DeckSummary, DeckUpdate, DeckView,
                        Language, Slide)
from app.slides_html import SlideTooLong, sanitize_slide_html

router = APIRouter()

_SLIDE_ID = re.compile(r"^[0-9a-f]{8}$")
CHAT_KEEP = 50


def _view(request: Request, deck: Deck) -> DeckView:
    return build_view(deck, request.app.state.store.list())


@router.post("/decks")
async def create_deck(
    request: Request,
    title: str = Form(min_length=1),
    language: Language = Form("el"),
    material_text: str = Form(""),
    files: list[UploadFile] | None = File(None),
) -> DeckView:
    pdfs = [await f.read() for f in files or []]
    try:
        material = await asyncio.to_thread(build_material, pdfs, material_text)
    except EmptyMaterialError as exc:
        raise HTTPException(422, str(exc)) from exc
    deck = request.app.state.decks.create(title=title.strip(), language=language, material_text=material)
    return _view(request, deck)


@router.get("/decks")
def list_decks(request: Request) -> list[DeckSummary]:
    projects = request.app.state.store.list()
    return [summarize(d, projects) for d in request.app.state.decks.list()]


@router.get("/decks/{deck_id}")
def get_deck(deck_id: str, request: Request) -> DeckView:
    return _view(request, request.app.state.decks.get(deck_id))


@router.get("/decks/{deck_id}/material")
def get_deck_material(deck_id: str, request: Request) -> PlainTextResponse:
    return PlainTextResponse(request.app.state.decks.material(deck_id))


@router.put("/decks/{deck_id}")
async def update_deck(deck_id: str, body: DeckUpdate, request: Request) -> DeckView:
    """The editor's autosave. Every slide is sanitised; the version guards against a stale tab."""
    decks = request.app.state.decks
    try:
        slides = [Slide(id=s.id if s.id and _SLIDE_ID.match(s.id) else new_slide_id(),
                        html=sanitize_slide_html(s.html), video=s.video) for s in body.slides]
    except SlideTooLong as exc:
        raise HTTPException(422, str(exc)) from exc

    def apply(deck: Deck) -> None:
        if deck.version != body.version:
            raise HTTPException(409, "The slides were changed elsewhere")
        deck.title = body.title.strip() or deck.title
        deck.slides = slides

    return _view(request, await decks.mutate(deck_id, apply))


@router.delete("/decks/{deck_id}", status_code=204)
async def delete_deck(deck_id: str, request: Request) -> None:
    """Removes the slides only: animations made from them are kept and simply unlinked."""
    store, decks = request.app.state.store, request.app.state.decks
    decks.get(deck_id)
    for project in store.list():
        if project.deck_id == deck_id:
            await store.mutate(project.id, lambda p: setattr(p, "deck_id", None))
    await decks.delete(deck_id)


@router.post("/decks/{deck_id}/chat")
async def chat(deck_id: str, body: DeckChatRequest, request: Request) -> DeckChatResult:
    """One message to the assistant: it answers and/or edits slides. Nothing is saved if the reply is unusable."""
    decks = request.app.state.decks
    deck = decks.get(deck_id)
    if body.slide_id and body.slide_id not in {s.id for s in deck.slides}:
        raise HTTPException(422, "This slide does not exist")
    try:
        reply, slides, log = await asyncio.to_thread(
            run_chat, request.app.state.llm, deck, decks.material(deck_id), body.message.strip(),
            slide_id=body.slide_id, selection=body.selection)
    except DeckChatError as exc:
        raise HTTPException(422, "The AI reply could not be applied. Please try again.") from exc
    except Exception as exc:  # noqa: BLE001 - Bedrock/network errors must reach the UI as a readable 502
        raise HTTPException(502, f"The AI model request failed: {exc}") from exc
    if await request.is_disconnected():
        raise HTTPException(499, "Cancelled")  # the professor pressed Stop while the model was answering
    now = datetime.now(timezone.utc)

    def apply(d: Deck) -> None:
        d.slides = slides
        d.chat = (d.chat + [ChatMessage(role="user", content=body.message.strip(), at=now),
                            ChatMessage(role="assistant", content=reply, edits=log, at=now)])[-CHAT_KEEP:]

    return DeckChatResult(deck=_view(request, await decks.mutate(deck_id, apply)), reply=reply, edits=log)
