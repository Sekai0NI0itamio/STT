from __future__ import annotations


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

