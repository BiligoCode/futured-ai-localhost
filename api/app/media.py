import subprocess
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
