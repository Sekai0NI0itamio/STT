from __future__ import annotations

from .models import ChunkPlan


def plan_chunks(duration_seconds: float, chunk_seconds: int) -> list[ChunkPlan]:
    if duration_seconds <= 0:
        raise ValueError("Audio duration must be greater than zero")
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be greater than zero")

    plans: list[ChunkPlan] = []
    remaining = duration_seconds
    start = 0.0
    index = 0
    while remaining > 0:
        duration = min(float(chunk_seconds), remaining)
        plans.append(
            ChunkPlan(
                chunk_id=f"chunk-{index:04d}",
                index=index,
                start_seconds=round(start, 3),
                duration_seconds=round(duration, 3),
            )
        )
        start += duration
        remaining = round(duration_seconds - start, 6)
        index += 1
    return plans


def merge_chunk_texts(chunk_texts: list[str]) -> str:
    parts = [text.strip() for text in chunk_texts if text and text.strip()]
    return "\n\n".join(parts).strip()

