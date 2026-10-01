import pytest

from app.media import assemble
from tests.conftest import make_clip, make_wav, probe

pytestmark = pytest.mark.slow


def test_audio_longer_than_video_holds_last_frame(tmp_path):
    v = make_clip(tmp_path / "v.mp4", 2)
    a = make_wav(tmp_path / "a.wav", 3)
    assemble([(v, a)], tmp_path / "out.mp4")
    p = probe(tmp_path / "out.mp4")
    assert abs(p["duration"] - 3.3) < 0.15 and p["has_audio"]
    assert (p["width"], p["height"], p["fps"]) == (1280, 720, 30)


def test_no_audio_gets_silent_track(tmp_path):
    v = make_clip(tmp_path / "v.mp4", 2)
    assemble([(v, None)], tmp_path / "out.mp4")
    p = probe(tmp_path / "out.mp4")
    assert abs(p["duration"] - 2.0) < 0.15 and p["has_audio"]


def test_audio_shorter_keeps_video_length(tmp_path):
    v = make_clip(tmp_path / "v.mp4", 3)
    a = make_wav(tmp_path / "a.wav", 1)
    assemble([(v, a)], tmp_path / "out.mp4")
    assert abs(probe(tmp_path / "out.mp4")["duration"] - 3.0) < 0.15


def test_mixed_resolutions_concat(tmp_path):
    v1 = make_clip(tmp_path / "v1.mp4", 2, "854x480", 15)
    a1 = make_wav(tmp_path / "a1.wav", 1)
    v2 = make_clip(tmp_path / "v2.mp4", 2, "1280x720", 30)
    assemble([(v1, a1), (v2, None)], tmp_path / "out.mp4")
    p = probe(tmp_path / "out.mp4")
    assert abs(p["duration"] - 4.0) < 0.2
    assert (p["width"], p["height"], p["fps"]) == (1280, 720, 30)
