import shutil
import subprocess
import tempfile
from pathlib import Path


class MediaError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip()[-1000:] or f"{cmd[0]} failed")
    return proc.stdout


def probe_duration(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    try:
        return float(out.strip())
    except ValueError as exc:
        raise MediaError(f"Could not read duration of {Path(path).name}") from exc


def normalize_audio(src: Path, dst: Path) -> None:
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ar", "44100", "-ac", "1", str(dst)])


TAIL_PAD_S = 0.3
VIDEO_FILTER = ("scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                "setsar=1,fps=30,tpad=stop_mode=clone:stop_duration={hold:.3f},format=yuv420p")
ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-ar", "44100", "-ac", "2", "-movflags", "+faststart"]


def _encode_segment(video: Path, audio: Path | None, out: Path) -> None:
    video_s = probe_duration(video)
    total = max(video_s, probe_duration(audio) + TAIL_PAD_S) if audio else video_s
    audio_input = ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    graph = (f"[0:v]{VIDEO_FILTER.format(hold=max(0.0, total - video_s))}[v];"
             "[1:a]aresample=44100,apad[a]")
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(video), *audio_input, "-filter_complex", graph,
          "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", *ENCODE, str(out)])


def assemble(segments: list[tuple[Path, Path | None]], out: Path) -> None:
    """Join (video, optional audio) segments into one MP4, holding each clip's last frame until its audio ends."""
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, (video, audio) in enumerate(segments):
            part = Path(tmp) / f"seg_{i}.mp4"
            _encode_segment(Path(video), Path(audio) if audio else None, part)
            parts.append(part)
        listing = Path(tmp) / "list.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
        tmp_out = Path(tmp) / "out.mp4"
        _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
              "-c", "copy", "-movflags", "+faststart", str(tmp_out)])
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_out), out)
