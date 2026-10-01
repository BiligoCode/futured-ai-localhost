import pytest
import subprocess

from app.media import MediaError, normalize_audio, probe_duration


@pytest.mark.slow
def test_normalize_mp3_to_wav(tmp_path, mp3_bytes):
    src = tmp_path / "a.mp3"
    src.write_bytes(mp3_bytes)
    dst = tmp_path / "a.wav"
    normalize_audio(src, dst)
    assert abs(probe_duration(dst) - 1.0) < 0.1


@pytest.mark.slow
def test_normalize_garbage_raises(tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"junk")
    with pytest.raises(MediaError):
        normalize_audio(src, tmp_path / "a.wav")


@pytest.mark.slow
def test_make_poster_real(tmp_path):
    from app.media import make_poster
    from tests.conftest import make_clip

    clip = make_clip(tmp_path / "clip.mp4", seconds=2)
    out = tmp_path / "posters" / "p.jpg"
    out.parent.mkdir()
    make_poster(clip, out, at=0.5)
    assert out.stat().st_size > 1000 and out.read_bytes()[:3] == b"\xff\xd8\xff"
    width = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True).stdout.strip()
    assert width == "640"
