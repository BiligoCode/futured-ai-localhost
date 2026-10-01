import asyncio
import logging
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


class JobRunner:
    """Runs keyed background coroutines; one job per key at a time."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def is_running(self, key: str) -> bool:
        return key in self._tasks

    def submit(self, key: str, factory: Callable[[], Awaitable[None]]) -> bool:
        if key in self._tasks:
            return False
        task = asyncio.create_task(self._run(factory))
        self._tasks[key] = task
        task.add_done_callback(lambda t, k=key: self._tasks.pop(k, None) if self._tasks.get(k) is t else None)
        return True

    @staticmethod
    async def _run(factory: Callable[[], Awaitable[None]]) -> None:
        try:
            await factory()
        except Exception:  # noqa: BLE001
            log.exception("background job failed")

    async def wait_all(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)
