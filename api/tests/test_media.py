import pytest

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
