import pytest

from app.main import create_app
from app.media import MediaError, probe_duration
from app.models import SceneDraft
from app.render import RenderResult
from tests.conftest import api_client, make_settings
from tests.fakes import FakeRenderer, FakeTTS, ScriptedLLM


def make_app(tmp_path, tts):
    app = create_app(make_settings(tmp_path), llm=ScriptedLLM([]), renderer=FakeRenderer([RenderResult(ok=True)]), tts=tts)
    p = app.state.store.create(title="t", concept="c", style="", tone="", language="el", material_text="m",
                               scenes=[SceneDraft(title=f"S{i}", visual="v", narration=f"Αφήγηση {i}") for i in range(3)])
    return app, p.id, [s.id for s in p.scenes]


def scene(app, pid, sid):
    return app.state.store.get(pid).scene(sid)


@pytest.mark.slow
async def test_ai_voice_for_scene(tmp_path, mp3_bytes):
    tts = FakeTTS(mp3_bytes)
    app, pid, sids = make_app(tmp_path, tts)
    async with api_client(app) as c:
        r = await c.post(f"/projects/{pid}/scenes/{sids[0]}/voice/ai")
        assert r.status_code == 200
        s = scene(app, pid, sids[0])
        assert (s.audio_source, s.audio_status) == ("ai", "done")
        audio = await c.get(f"/projects/{pid}/scenes/{sids[0]}/audio")
        assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
    assert tts.calls == [("Αφήγηση 0", "el")]


async def test_ai_voice_failure_502(tmp_path):
    app, pid, sids = make_app(tmp_path, FakeTTS(b"", fail=True))
    async with api_client(app) as c:
        r = await c.post(f"/projects/{pid}/scenes/{sids[0]}/voice/ai")
    assert r.status_code == 502 and "401" in r.json()["detail"]
    assert scene(app, pid, sids[0]).audio_status == "failed"


async def test_audio_404_when_none(tmp_path):
    app, pid, sids = make_app(tmp_path, FakeTTS(b""))
    async with api_client(app) as c:
        assert (await c.get(f"/projects/{pid}/scenes/{sids[0]}/audio")).status_code == 404


@pytest.mark.slow
async def test_ai_all_skips_done(tmp_path, mp3_bytes):
    tts = FakeTTS(mp3_bytes)
    app, pid, sids = make_app(tmp_path, tts)
    async with api_client(app) as c:
        await c.post(f"/projects/{pid}/scenes/{sids[0]}/voice/ai")
        r = await c.post(f"/projects/{pid}/voice/ai-all")
    assert r.status_code == 200
    assert len(tts.calls) == 3
    assert all(s.audio_status == "done" for s in app.state.store.get(pid).scenes)


@pytest.mark.slow
async def test_narration_edit_clears_ai_audio(tmp_path, mp3_bytes):
    app, pid, sids = make_app(tmp_path, FakeTTS(mp3_bytes))
    async with api_client(app) as c:
        await c.post(f"/projects/{pid}/scenes/{sids[0]}/voice/ai")
        r = await c.patch(f"/projects/{pid}/scenes/{sids[0]}", json={"narration": "Νέο κείμενο"})
    assert r.status_code == 200
    s = scene(app, pid, sids[0])
    assert (s.narration, s.audio_status, s.audio_source) == ("Νέο κείμενο", "none", None)
    assert not (app.state.store.scene_dir(pid, sids[0]) / "audio.wav").exists()


async def test_narration_edit_keeps_professor_audio(tmp_path):
    app, pid, sids = make_app(tmp_path, FakeTTS(b""))
    await app.state.store.update_scene(pid, sids[0], audio_source="professor", audio_status="done")
    async with api_client(app) as c:
        await c.patch(f"/projects/{pid}/scenes/{sids[0]}", json={"narration": "Νέο"})
    s = scene(app, pid, sids[0])
    assert (s.audio_source, s.audio_status) == ("professor", "done")


def recording(data: bytes):
    return {"file": ("take.webm", data, "audio/webm")}


@pytest.mark.slow
async def test_recording_without_duration_metadata(tmp_path, webm_no_duration):
    no_meta = tmp_path / "raw.webm"
    no_meta.write_bytes(webm_no_duration)
    with pytest.raises(MediaError):
        probe_duration(no_meta)  # proves the fixture really lacks duration metadata
    app, pid, sids = make_app(tmp_path, FakeTTS(b""))
    async with api_client(app) as c:
        r = await c.post(f"/projects/{pid}/scenes/{sids[0]}/voice/recording", files=recording(webm_no_duration))
    assert r.status_code == 200
    s = scene(app, pid, sids[0])
    assert (s.audio_source, s.audio_status) == ("professor", "done")
    d = app.state.store.scene_dir(pid, sids[0])
    assert abs(probe_duration(d / "audio.wav") - 1.5) < 0.15
    assert (d / "voice.webm").exists()


@pytest.mark.slow
async def test_bad_recording_keeps_previous_audio(tmp_path, mp3_bytes):
    app, pid, sids = make_app(tmp_path, FakeTTS(mp3_bytes))
    async with api_client(app) as c:
        await c.post(f"/projects/{pid}/scenes/{sids[0]}/voice/ai")
        wav = app.state.store.scene_dir(pid, sids[0]) / "audio.wav"
        before = wav.read_bytes()
        r = await c.post(f"/projects/{pid}/scenes/{sids[0]}/voice/recording", files=recording(b"junk"))
    assert r.status_code == 422 and r.json()["detail"] == "Could not read the recording"
    s = scene(app, pid, sids[0])
    assert (s.audio_source, s.audio_status) == ("ai", "done")
    assert wav.read_bytes() == before


@pytest.mark.slow
async def test_clear_voice(tmp_path, webm_no_duration):
    app, pid, sids = make_app(tmp_path, FakeTTS(b""))
    async with api_client(app) as c:
        await c.post(f"/projects/{pid}/scenes/{sids[0]}/voice/recording", files=recording(webm_no_duration))
        r = await c.delete(f"/projects/{pid}/scenes/{sids[0]}/voice")
    assert r.status_code == 200
    s = scene(app, pid, sids[0])
    assert (s.audio_source, s.audio_status) == (None, "none")
    d = app.state.store.scene_dir(pid, sids[0])
    assert not (d / "audio.wav").exists() and not (d / "voice.webm").exists()


async def test_narration_empty_422(tmp_path):
    app, pid, sids = make_app(tmp_path, FakeTTS(b""))
    async with api_client(app) as c:
        r = await c.patch(f"/projects/{pid}/scenes/{sids[0]}", json={"narration": ""})
    assert r.status_code == 422
