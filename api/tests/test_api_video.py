"""The single-video flow: scenes compose into one preview, a whole-video recording with pauses becomes the final
video, and change requests about the video are routed to the right scene."""
import json

import pytest

from app.main import create_app
from app.models import SceneDraft
from app.render import RenderResult
from tests.conftest import api_client, ffmpeg_bytes, make_clip, make_settings, probe
from tests.fakes import VALID_CODE, FakeRenderer, FakeTTS, ScriptedLLM


class ClipRenderer(FakeRenderer):
    """Renders a real 2-second test clip, so the videos can be composed with ffmpeg."""

    def __init__(self):
        super().__init__([RenderResult(ok=True)])

    async def __call__(self, code_path, output_path):
        self.calls.append((code_path, output_path))
        make_clip(output_path, 2)
        return RenderResult(ok=True)


def make_app(tmp_path, llm_replies=(), tts=None):
    app = create_app(make_settings(tmp_path), llm=ScriptedLLM(list(llm_replies)), renderer=ClipRenderer(),
                     tts=tts or FakeTTS(b""))
    p = app.state.store.create(title="Δυαδική αναζήτηση", concept="c", style="", language="el", material_text="m",
                               scenes=[SceneDraft(title=f"S{i}", visual="v", narration="n") for i in range(2)])
    return app, p.id, [s.id for s in p.scenes]


async def render_all(app, c, pid, sids):
    for sid in sids:
        scene_dir = app.state.store.scene_dir(pid, sid)
        (scene_dir / "code_v1.py").write_text(VALID_CODE, encoding="utf-8")
        make_clip(scene_dir / "render_v1.mp4", 2)
        await app.state.store.update_scene(pid, sid, code_version=1, render_status="done")
    await app.state.store.mutate(pid, lambda p: setattr(p, "stage", "scenes"))
    r = await c.post(f"/projects/{pid}/compose")
    assert r.json()["preview"]["status"] == "building"
    await app.state.jobs.wait_all()


def spans(cut):
    return [(round(s["start"], 1), round(s["end"], 1)) for s in cut["segments"]]


@pytest.mark.slow
async def test_preview_then_recorded_narration_with_pause(tmp_path):
    app, pid, sids = make_app(tmp_path)
    async with api_client(app) as c:
        await render_all(app, c, pid, sids)
        p = (await c.get(f"/projects/{pid}")).json()
        assert p["preview"]["status"] == "done" and not p["preview_outdated"]
        assert spans(p["preview"]) == [(0, 2), (2, 4)]
        assert (await c.get(f"/projects/{pid}/preview.mp4")).status_code == 200

        # The professor talks for 7 s, pausing the animation at 1 s for 2 s.
        take = ffmpeg_bytes("-f", "lavfi", "-i", "sine=frequency=300:duration=7", "-c:a", "libopus", "-f", "webm",
                            "pipe:1")
        r = await c.post(f"/projects/{pid}/narration/recording", files={"file": ("take.webm", take)},
                         data={"from_scene": sids[0], "holds": json.dumps([{"at": 1, "duration": 2}])})
        assert r.status_code == 200, r.text
        s0, s1 = r.json()["scenes"]
        assert (s0["audio_source"], s0["holds"], s1["holds"]) == ("professor", [{"at": 1.0, "duration": 2.0}], [])
        await app.state.jobs.wait_all()

        p = (await c.get(f"/projects/{pid}")).json()
        # Scene 1: 2 s of animation + 2 s pause (its 4 s of audio + tail pad); scene 2: the remaining 3 s of audio.
        assert p["final"]["status"] == "done" and spans(p["final"]) == [(0, 4.3), (4.3, 7.6)]
        r = await c.post(f"/projects/{pid}/export")
        assert r.json() == {"url": f"/projects/{pid}/export.mp4"}
    assert abs(probe(app.state.store.project_dir(pid) / "export.mp4")["duration"] - 7.6) < 0.2


@pytest.mark.slow
async def test_recording_rejected_when_video_changed(tmp_path):
    app, pid, sids = make_app(tmp_path)
    async with api_client(app) as c:
        await render_all(app, c, pid, sids)
        await app.state.store.update_scene(pid, sids[1], code_version=2)
        r = await c.post(f"/projects/{pid}/narration/recording", files={"file": ("take.webm", b"x")},
                         data={"from_scene": sids[0]})
    assert r.status_code == 409 and "changed while you were recording" in r.json()["detail"]


@pytest.mark.slow
async def test_ai_narration_for_whole_video(tmp_path, mp3_bytes):
    tts = FakeTTS(mp3_bytes)
    app, pid, sids = make_app(tmp_path, tts=tts)
    async with api_client(app) as c:
        await render_all(app, c, pid, sids)
        r = await c.post(f"/projects/{pid}/narration/ai")
        assert r.json()["narrating"] is True
        await app.state.jobs.wait_all()
        p = (await c.get(f"/projects/{pid}")).json()
    assert len(tts.calls) == 2 and not p["narrating"]
    assert all(s["audio_source"] == "ai" for s in p["scenes"]) and p["final"]["status"] == "done"


@pytest.mark.slow
async def test_change_request_is_routed_to_the_scene_at_the_timestamp(tmp_path):
    route = json.dumps({"edits": [{"part": 2, "animation": True, "instruction": "Put each number in its box",
                                   "narration": None, "summary": "Οι αριθμοί μπαίνουν στα κουτιά τους"}]})
    app, pid, sids = make_app(tmp_path, [route, VALID_CODE])
    async with api_client(app) as c:
        await render_all(app, c, pid, sids)
        r = await c.post(f"/projects/{pid}/revise",
                         json={"instruction": "στο 0:03 οι αριθμοί είναι όλοι στη μέση", "at_seconds": 3.1})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["edits"] == [{"scene_id": sids[1], "start": 2.0, "end": 4.0, "animation": True,
                                  "narration": False, "summary": "Οι αριθμοί μπαίνουν στα κουτιά τους"}]
        assert body["project"]["scenes"][1]["render_status"] == "generating"
        await app.state.jobs.wait_all()
        p = (await c.get(f"/projects/{pid}")).json()
    assert [s["code_version"] for s in p["scenes"]] == [1, 2]
    assert "0:03 in the request falls in part 2" in app.state.llm.calls[0][1][0]["content"]
    assert "Put each number in its box" in app.state.llm.calls[1][1][0]["content"]
    assert p["preview"]["version"] == 2 and not p["preview_outdated"]


@pytest.mark.slow
async def test_narration_change_regenerates_ai_voice(tmp_path, mp3_bytes):
    route = json.dumps({"edits": [{"part": 1, "animation": False, "instruction": "", "narration": "Απλούστερα.",
                                   "summary": "Πιο απλή εξήγηση"}]}, ensure_ascii=False)
    tts = FakeTTS(mp3_bytes)
    app, pid, sids = make_app(tmp_path, [route], tts=tts)
    async with api_client(app) as c:
        await render_all(app, c, pid, sids)
        await c.post(f"/projects/{pid}/narration/ai")
        await app.state.jobs.wait_all()
        r = await c.post(f"/projects/{pid}/revise", json={"instruction": "πες την αρχή πιο απλά"})
        assert r.status_code == 200, r.text
        await app.state.jobs.wait_all()
        p = (await c.get(f"/projects/{pid}")).json()
    assert tts.calls[-1][0] == "Απλούστερα."
    assert p["scenes"][0]["code_version"] == 1 and p["scenes"][0]["audio_version"] == 2
    assert p["final"]["status"] == "done" and not p["final_outdated"]


async def test_revise_before_ready_409(tmp_path):
    app, pid, _ = make_app(tmp_path)
    async with api_client(app) as c:
        r = await c.post(f"/projects/{pid}/revise", json={"instruction": "x"})
    assert r.status_code == 409
