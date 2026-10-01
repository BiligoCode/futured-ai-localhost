from fastapi import FastAPI

from app.compose import mark_pending, refresh_cuts


async def schedule_refresh(app: FastAPI, project_id: str) -> None:
    """Rebuild the project's videos in the background after its scenes or narration changed."""
    store = app.state.store
    await mark_pending(store, project_id)
    app.state.jobs.submit_coalesced(f"cuts:{project_id}", lambda: refresh_cuts(store, project_id))
