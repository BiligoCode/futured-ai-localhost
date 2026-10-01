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


def cut_audio(src: Path, start: float, end: float | None, dst: Path) -> None:
    """Copy [start, end) of a wav (to its end when `end` is None) into `dst`."""
    until = ["-to", f"{end:.3f}"] if end is not None else []
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ss", f"{start:.3f}", *until, "-ar", "44100", "-ac", "1",
          str(dst)])


TAIL_PAD_S = 0.3
MIN_PIECE_S = 0.05
BASE_FILTER = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
HOLD = "tpad=stop_mode=clone:stop_duration={:.3f}"
ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-ar", "44100", "-ac", "2", "-movflags", "+faststart"]


def _video_graph(video_s: float, holds: list[tuple[float, float]], tail: float) -> str:
    """Filter graph that freezes the frame at each hold point for the hold's duration, then holds the last frame."""
    cuts: dict[float, float] = {}
    for at, duration in holds:
        at = min(max(at, MIN_PIECE_S), video_s)
        if at > video_s - MIN_PIECE_S:
            tail += duration
        else:
            cuts[round(at, 3)] = cuts.get(round(at, 3), 0.0) + duration
    if not cuts:
        return f"[0:v]{BASE_FILTER},{HOLD.format(tail)},format=yuv420p[v]"
    points = sorted(cuts)
    bounds = [0.0, *points, video_s]
    n = len(bounds) - 1
    parts = [f"[0:v]{BASE_FILTER},split={n}" + "".join(f"[p{i}]" for i in range(n))]
    for i in range(n):
        start, end = bounds[i], bounds[i + 1]
        trim = f"trim=start={start:.3f}" + (f":end={end:.3f}" if i < n - 1 else "")
        hold = cuts[end] if i < n - 1 else 0.0
        parts.append(f"[p{i}]{trim},setpts=PTS-STARTPTS,{HOLD.format(hold)}[q{i}]")
    parts.append("".join(f"[q{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,{HOLD.format(tail)},format=yuv420p[v]")
    return ";".join(parts)


def encode_segment(video: Path, audio: Path | None, out: Path, holds: list[tuple[float, float]] = ()) -> float:
    """Encode one scene: its animation with frozen frames at each hold, and its narration.

    The last frame is held until the narration ends. Returns the segment's duration in seconds.
    """
    video_s = probe_duration(video)
    held_s = video_s + sum(d for _, d in holds)
    total = max(held_s, probe_duration(audio) + TAIL_PAD_S) if audio else held_s
    audio_input = ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    graph = f"{_video_graph(video_s, list(holds), max(0.0, total - held_s))};[1:a]aresample=44100,apad[a]"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(video), *audio_input, "-filter_complex", graph,
          "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", *ENCODE, str(out)])
    return probe_duration(out)


def concat(parts: list[Path], out: Path) -> None:
    """Join segments produced by `encode_segment` (same codecs) into one MP4 without re-encoding."""
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "list.txt"
        listing.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in parts), encoding="utf-8")
        tmp_out = Path(tmp) / "out.mp4"
        _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
              "-c", "copy", "-movflags", "+faststart", str(tmp_out)])
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_out), out)


def assemble(segments: list[tuple[Path, Path | None]], out: Path) -> None:
    """Join (video, optional audio) segments into one MP4, holding each clip's last frame until its audio ends."""
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, (video, audio) in enumerate(segments):
            part = Path(tmp) / f"seg_{i}.mp4"
            encode_segment(Path(video), Path(audio) if audio else None, part)
            parts.append(part)
        concat(parts, out)
