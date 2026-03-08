from __future__ import annotations

import json
from pathlib import Path
import subprocess


class FFmpegError(RuntimeError):
    pass


def probe_duration_seconds(audio_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(audio_path),
    ]
    completed = _run(command)
    payload = json.loads(completed.stdout or "{}")
    duration = float(payload.get("format", {}).get("duration", 0.0))
    if duration <= 0:
        raise FFmpegError(f"ffprobe returned invalid duration for {audio_path}")
    return duration


def normalize_audio(
    input_path: Path,
    output_path: Path,
    sample_rate_hz: int,
    audio_channels: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        str(audio_channels),
        "-ar",
        str(sample_rate_hz),
        str(output_path),
    ]
    _run(command)


def extract_chunk(input_path: Path, output_path: Path, start_seconds: float, duration_seconds: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{duration_seconds:.3f}",
        "-i",
        str(input_path),
        "-acodec",
        "pcm_s16le",
        str(output_path),
    ]
    _run(command)


def extract_chunk_mp3(
    input_path: Path,
    output_path: Path,
    start_seconds: float,
    duration_seconds: float,
    sample_rate_hz: int,
    audio_channels: int,
    bitrate_kbps: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{duration_seconds:.3f}",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        str(audio_channels),
        "-ar",
        str(sample_rate_hz),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate_kbps}k",
        str(output_path),
    ]
    _run(command)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise FFmpegError(f"Command failed: {' '.join(command)}\n{stderr}")
    return completed
