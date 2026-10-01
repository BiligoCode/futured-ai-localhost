import pytest

from app.media import assemble, concat, cut_audio, encode_segment, probe_duration
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


def test_holds_freeze_frames_mid_clip(tmp_path):
    v = make_clip(tmp_path / "v.mp4", 3)
    out = tmp_path / "seg.mp4"
    total = encode_segment(v, None, out, holds=[(1.0, 2.0), (2.0, 0.5)])
    assert abs(total - 5.5) < 0.15
    assert abs(probe(out)["duration"] - 5.5) < 0.15


def test_holds_at_edges_and_audio_tail(tmp_path):
    v = make_clip(tmp_path / "v.mp4", 2)
    a = make_wav(tmp_path / "a.wav", 6)
    # A hold at the very start and one at the end of the clip; the narration is longer still.
    total = encode_segment(v, a, tmp_path / "seg.mp4", holds=[(0.0, 1.0), (2.0, 1.5)])
    assert abs(total - 6.3) < 0.15


def test_concat_segments(tmp_path):
    parts = []
    for i, secs in enumerate((1, 2)):
        part = tmp_path / f"p{i}.mp4"
        encode_segment(make_clip(tmp_path / f"v{i}.mp4", secs), None, part)
        parts.append(part)
    concat(parts, tmp_path / "out.mp4")
    assert abs(probe(tmp_path / "out.mp4")["duration"] - 3.0) < 0.2


def test_cut_audio(tmp_path):
    src = make_wav(tmp_path / "a.wav", 4)
    cut_audio(src, 1.0, 2.5, tmp_path / "c1.wav")
    cut_audio(src, 3.0, None, tmp_path / "c2.wav")
    assert abs(probe_duration(tmp_path / "c1.wav") - 1.5) < 0.05
    assert abs(probe_duration(tmp_path / "c2.wav") - 1.0) < 0.05
