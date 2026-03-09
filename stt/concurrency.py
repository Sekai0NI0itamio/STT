from __future__ import annotations

import os


UNLIMITED_SENTINELS = {"0", "all", "auto", "max", "unlimited"}


def parse_parallel_setting(value: object) -> int:
    if value is None:
        raise ValueError("parallel setting cannot be None")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("parallel setting cannot be negative")
        return value

    text = str(value).strip().lower()
    if text in UNLIMITED_SENTINELS:
        return 0
    parsed = int(text)
    if parsed < 0:
        raise ValueError("parallel setting cannot be negative")
    return parsed


def resolve_parallel_workers(configured: int, task_count: int) -> int:
    if task_count <= 0:
        return 1
    if configured <= 0:
        return task_count
    return min(configured, task_count)


def resolve_transcription_workers(model: str, task_count: int, cpu_count: int | None = None) -> int:
    if task_count <= 0:
        return 1

    available_cpus = max(int(cpu_count if cpu_count is not None else (os.cpu_count() or 1)), 1)
    normalized_model = model.strip().lower()

    if normalized_model.startswith("large"):
        recommended = max(1, available_cpus // 2)
    elif normalized_model == "medium":
        recommended = available_cpus
    else:
        recommended = task_count

    return min(task_count, max(recommended, 1))
