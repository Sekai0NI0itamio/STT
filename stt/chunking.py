from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .config import STTConfig
from .models import ChunkPlan


def plan_chunks(duration_seconds: float, chunk_seconds: int) -> list[ChunkPlan]:
    if duration_seconds <= 0:
        raise ValueError("Audio duration must be greater than zero")
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be greater than zero")

    duration_ms = int(round(duration_seconds * 1000))
    chunk_ms = int(round(chunk_seconds * 1000))
    ranges = _split_range(0, duration_ms, chunk_ms)
    return ranges_to_chunk_plans(ranges)


def merge_chunk_texts(chunk_texts: list[str]) -> str:
    parts = [text.strip() for text in chunk_texts if text and text.strip()]
    return "\n\n".join(parts).strip()


def build_chunk_plans(
    normalized_audio_path: Path,
    config: STTConfig,
) -> tuple[list[ChunkPlan], dict[str, object]]:
    audio, duration_ms = load_audio(normalized_audio_path)
    max_duration_ms = calculate_max_chunk_duration_ms(config)
    raw_ranges = detect_nonsilent_ranges(
        audio_segment=audio,
        min_silence_len_ms=config.min_silence_len_ms,
        silence_thresh_dbfs=config.silence_thresh_dbfs,
    )
    expanded_ranges = expand_ranges(raw_ranges, duration_ms, config.keep_silence_ms)
    ranges = group_ranges_into_chunks(expanded_ranges, duration_ms, max_duration_ms)
    metadata = {
        "strategy": "silence-aware-mp3",
        "duration_ms": duration_ms,
        "raw_speech_ranges_ms": [[start, end] for start, end in raw_ranges],
        "expanded_speech_ranges_ms": [[start, end] for start, end in expanded_ranges],
        "max_chunk_duration_ms": max_duration_ms,
        "target_chunk_size_mb": config.max_input_mb,
        "target_chunk_bitrate_kbps": config.chunk_bitrate_kbps,
        "chunk_size_safety_margin": config.chunk_size_safety_margin,
        "min_silence_len_ms": config.min_silence_len_ms,
        "silence_thresh_dbfs": config.silence_thresh_dbfs,
        "keep_silence_ms": config.keep_silence_ms,
    }
    return ranges_to_chunk_plans(ranges), metadata


def calculate_max_chunk_duration_ms(config: STTConfig) -> int:
    duration_from_bitrate = max_chunk_duration_ms(
        max_chunk_bytes=config.max_input_bytes,
        bitrate_kbps=config.chunk_bitrate_kbps,
        safety_margin=config.chunk_size_safety_margin,
    )
    return min(duration_from_bitrate, config.chunk_seconds * 1000)


def max_chunk_duration_ms(max_chunk_bytes: int, bitrate_kbps: int, safety_margin: float) -> int:
    if max_chunk_bytes <= 0:
        raise ValueError("max_chunk_bytes must be greater than zero")
    if bitrate_kbps <= 0:
        raise ValueError("bitrate_kbps must be greater than zero")
    if not 0 < safety_margin <= 1:
        raise ValueError("safety_margin must be between 0 and 1")

    bitrate_bps = bitrate_kbps * 1000
    duration_seconds = (max_chunk_bytes * 8) / bitrate_bps
    return max(int(duration_seconds * safety_margin * 1000), 1000)


def group_ranges_into_chunks(
    speech_ranges_ms: Iterable[tuple[int, int]],
    total_duration_ms: int,
    max_chunk_duration_ms: int,
) -> list[tuple[int, int]]:
    if total_duration_ms <= 0:
        raise ValueError("total_duration_ms must be greater than zero")
    if max_chunk_duration_ms <= 0:
        raise ValueError("max_chunk_duration_ms must be greater than zero")

    normalized_ranges = _normalize_ranges(speech_ranges_ms, total_duration_ms)
    if not normalized_ranges:
        return _split_range(0, total_duration_ms, max_chunk_duration_ms)

    chunks: list[tuple[int, int]] = []
    current_start: int | None = None
    current_end: int | None = None

    for start_ms, end_ms in normalized_ranges:
        if current_start is None or current_end is None:
            current_start, current_end = start_ms, end_ms
            continue

        if end_ms - current_start <= max_chunk_duration_ms:
            current_end = end_ms
            continue

        chunks.extend(_split_range(current_start, current_end, max_chunk_duration_ms))
        current_start, current_end = start_ms, end_ms

    if current_start is not None and current_end is not None:
        chunks.extend(_split_range(current_start, current_end, max_chunk_duration_ms))

    return chunks


def expand_ranges(
    speech_ranges_ms: Iterable[tuple[int, int]],
    total_duration_ms: int,
    keep_silence_ms: int,
) -> list[tuple[int, int]]:
    if total_duration_ms <= 0:
        raise ValueError("total_duration_ms must be greater than zero")
    if keep_silence_ms < 0:
        raise ValueError("keep_silence_ms must be zero or greater")

    expanded: list[tuple[int, int]] = []
    for start_ms, end_ms in speech_ranges_ms:
        start_ms = max(0, int(start_ms) - keep_silence_ms)
        end_ms = min(total_duration_ms, int(end_ms) + keep_silence_ms)
        if end_ms <= start_ms:
            continue
        expanded.append((start_ms, end_ms))

    return _normalize_ranges(expanded, total_duration_ms)


def ranges_to_chunk_plans(ranges_ms: Iterable[tuple[int, int]]) -> list[ChunkPlan]:
    plans: list[ChunkPlan] = []
    for index, (start_ms, end_ms) in enumerate(ranges_ms):
        duration_ms = max(0, end_ms - start_ms)
        if duration_ms <= 0:
            continue
        plans.append(
            ChunkPlan(
                chunk_id=f"chunk-{index:04d}",
                index=index,
                start_seconds=round(start_ms / 1000.0, 3),
                duration_seconds=round(duration_ms / 1000.0, 3),
            )
        )
    return plans


def detect_nonsilent_ranges(
    audio_segment: object,
    min_silence_len_ms: int,
    silence_thresh_dbfs: int,
) -> list[tuple[int, int]]:
    try:
        from pydub.silence import detect_nonsilent
    except ImportError as exc:
        raise RuntimeError(
            "pydub is required for silence-aware chunk planning. Install the runtime extras."
        ) from exc

    detected = detect_nonsilent(
        audio_segment,
        min_silence_len=min_silence_len_ms,
        silence_thresh=silence_thresh_dbfs,
    )
    return [(int(start_ms), int(end_ms)) for start_ms, end_ms in detected]


def load_audio(audio_path: Path) -> tuple[object, int]:
    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise RuntimeError("pydub is required for silence-aware chunk planning.") from exc

    audio = AudioSegment.from_file(audio_path)
    return audio, int(len(audio))


def _normalize_ranges(
    ranges_ms: Iterable[tuple[int, int]],
    total_duration_ms: int,
) -> list[tuple[int, int]]:
    clamped = []
    for start_ms, end_ms in ranges_ms:
        start_ms = max(0, min(int(start_ms), total_duration_ms))
        end_ms = max(0, min(int(end_ms), total_duration_ms))
        if end_ms <= start_ms:
            continue
        clamped.append((start_ms, end_ms))

    clamped.sort(key=lambda item: item[0])
    merged: list[tuple[int, int]] = []
    for start_ms, end_ms in clamped:
        if not merged or start_ms > merged[-1][1]:
            merged.append((start_ms, end_ms))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end_ms))
    return merged


def _split_range(start_ms: int, end_ms: int, max_chunk_duration_ms: int) -> list[tuple[int, int]]:
    chunks: list[tuple[int, int]] = []
    cursor = start_ms
    while cursor < end_ms:
        next_end = min(cursor + max_chunk_duration_ms, end_ms)
        chunks.append((cursor, next_end))
        cursor = next_end
    return chunks
