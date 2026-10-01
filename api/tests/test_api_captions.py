"""Burned-in captions for the AI voice, and server messages in the dashboard's language."""
import subprocess

import pytest

from tests.conftest import api_client, ffmpeg_bytes
from tests.fakes import FakeTTS
from tests.test_api_video import make_app


class TimedTTS(FakeTTS):
    def synthesize_timed(self, text, language):
        self.calls.append((text, language))
        n = len(text)
        return self.audio, {"characters": list(text), "character_start_times_seconds": [i / n for i in range(n)],
                            "character_end_times_seconds": [(i + 1) / n for i in range(n)]}


def bottom_strip_brightness(video, t=0.5) -> float:
    """Mean brightness of the bottom 15% of the frame at `t` seconds (black animation: captions light it up)."""
    raw = ffmpeg_bytes("-ss", str(t), "-i", str(video), "-frames:v", "1", "-vf",
                       "crop=iw:ih*0.15:0:ih*0.85,scale=64:8", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1")
    return sum(raw) / len(raw)


@pytest.mark.slow
async def test_captions_are_burned_into_ai_narrated_video(tmp_path, mp3_bytes):
    app, pid, sids = make_app(tmp_path, tts=TimedTTS(mp3_bytes))
    store = app.state.store
    async with api_client(app) as c:
        for sid in sids:  # a black animation, so only captions can light up the bottom strip
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:size=854x480:rate=15:d=2",
                            "-pix_fmt", "yuv420p", str(store.scene_dir(pid, sid) / "render_v1.mp4")], check=True)
            await store.update_scene(pid, sid, code_version=1, render_status="done",
                                     narration="Ψάχνουμε το κλειδί στον ταξινομημένο πίνακα με δυαδική αναζήτηση.")
        await store.mutate(pid, lambda p: setattr(p, "stage", "scenes"))
        await c.post(f"/projects/{pid}/narration/ai")
        await app.state.jobs.wait_all()
        export = store.project_dir(pid) / "export.mp4"
        plain = bottom_strip_brightness(export)

        r = await c.patch(f"/projects/{pid}/settings", json={"captions": True})
        assert r.json()["captions"] is True and r.json()["final_outdated"] is True
        await app.state.jobs.wait_all()
        p = (await c.get(f"/projects/{pid}")).json()
    assert p["final"]["status"] == "done" and not p["final_outdated"]
    assert (store.scene_dir(pid, sids[0]) / "captions.json").is_file()
    assert plain < 2 and bottom_strip_brightness(export) > plain + 10


async def test_server_messages_follow_dashboard_language(tmp_path):
    app, pid, _ = make_app(tmp_path)
    async with api_client(app) as c:
        en = await c.post(f"/projects/{pid}/revise", json={"instruction": "x"})
        el = await c.post(f"/projects/{pid}/revise", json={"instruction": "x"}, headers={"X-Lara-Lang": "el"})
        missing = await c.get("/projects/nope", headers={"X-Lara-Lang": "el"})
    assert en.json()["detail"] == "Wait until the video is ready before asking for changes"
    assert el.json()["detail"] == "Περιμένετε να ετοιμαστεί το βίντεο πριν ζητήσετε αλλαγές"
    assert missing.json()["detail"] == "Το έργο δεν βρέθηκε"
