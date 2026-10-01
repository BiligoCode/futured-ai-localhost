"""Decks on disk: `data/decks/<id>/deck.json` + `material.txt`, the same shape as ProjectStore."""
import asyncio
import html
import os
import shutil
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.models import Deck, DeckNotFound, Slide

__all__ = ["DeckNotFound", "DeckStore", "new_slide_id"]


def new_slide_id() -> str:
    return uuid.uuid4().hex[:8]


class DeckStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.decks_dir = self.root / "decks"
        self.decks_dir.mkdir(parents=True, exist_ok=True)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def deck_dir(self, deck_id: str) -> Path:
        return self.decks_dir / deck_id

    def create(self, *, title: str, language: str, material_text: str) -> Deck:
        now = datetime.now(timezone.utc)
        deck = Deck(
            id=uuid.uuid4().hex[:10],
            created_at=now,
            updated_at=now,
            title=title,
            language=language,
            slides=[Slide(id=new_slide_id(), html=f"<h1>{html.escape(title, quote=False)}</h1>")],
        )
        self.deck_dir(deck.id).mkdir(parents=True)
        (self.deck_dir(deck.id) / "material.txt").write_text(material_text, encoding="utf-8")
        self.write(deck)
        return deck

    def get(self, deck_id: str) -> Deck:
        path = self.deck_dir(deck_id) / "deck.json"
        if not deck_id or "/" in deck_id or not path.is_file():
            raise DeckNotFound(deck_id)
        return Deck.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[Deck]:
        decks = [self.get(p.name) for p in self.decks_dir.iterdir() if (p / "deck.json").is_file()]
        return sorted(decks, key=lambda d: d.created_at, reverse=True)

    def material(self, deck_id: str) -> str:
        self.get(deck_id)
        return (self.deck_dir(deck_id) / "material.txt").read_text(encoding="utf-8")

    def write(self, deck: Deck) -> None:
        path = self.deck_dir(deck.id) / "deck.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(deck.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def save(self, deck: Deck) -> None:
        deck.updated_at = datetime.now(timezone.utc)
        deck.version += 1
        self.write(deck)

    async def mutate(self, deck_id: str, fn: Callable[[Deck], None]) -> Deck:
        async with self._locks[deck_id]:
            deck = self.get(deck_id)
            fn(deck)
            self.save(deck)
            return deck

    async def delete(self, deck_id: str) -> None:
        self.get(deck_id)
        async with self._locks[deck_id]:
            shutil.rmtree(self.deck_dir(deck_id), ignore_errors=True)
        self._locks.pop(deck_id, None)
