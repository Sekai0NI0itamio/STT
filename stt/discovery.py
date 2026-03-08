from __future__ import annotations

from fnmatch import fnmatchcase
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from .config import STTConfig
from .models import InputCandidate


def discover_inputs(config: STTConfig, file_glob: str | None = None) -> list[InputCandidate]:
    incoming_dir = config.incoming_dir_abs
    if not incoming_dir.exists():
        return []

    candidates: list[InputCandidate] = []
    for path in incoming_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".mp3":
            continue
        relpath = path.relative_to(config.root_dir).as_posix()
        if file_glob and not matches_file_glob(relpath, file_glob):
            continue
        size_bytes = path.stat().st_size
        validation_errors: list[str] = []
        if size_bytes > config.max_input_bytes:
            validation_errors.append(
                f"Input file exceeds max_input_mb={config.max_input_mb}: {size_bytes} bytes"
            )
        candidates.append(
            InputCandidate(
                relpath=relpath,
                abs_path=path.resolve(),
                size_bytes=size_bytes,
                slug=build_slug(relpath),
                validation_errors=validation_errors,
            )
        )

    return sorted(candidates, key=lambda candidate: candidate.relpath)


def build_slug(relpath: str) -> str:
    stem = "".join(ch.lower() if ch.isalnum() else "-" for ch in relpath).strip("-")
    digest = hashlib.sha256(relpath.encode("utf-8")).hexdigest()[:8]
    compact = "-".join(part for part in stem.split("-") if part)
    compact = compact[:48].rstrip("-") or "input"
    return f"{compact}-{digest}"


def matches_file_glob(relpath: str, pattern: str) -> bool:
    path_parts = tuple(part.lower() for part in relpath.split("/") if part)
    pattern_parts = tuple(part.lower() for part in pattern.split("/") if part)

    @lru_cache(maxsize=None)
    def _match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        token = pattern_parts[pattern_index]
        if token == "**":
            if _match(path_index, pattern_index + 1):
                return True
            if path_index < len(path_parts):
                return _match(path_index + 1, pattern_index)
            return False
        if path_index >= len(path_parts):
            return False
        if not fnmatchcase(path_parts[path_index], token):
            return False
        return _match(path_index + 1, pattern_index + 1)

    return _match(0, 0)


def build_discovery_manifest(
    config: STTConfig,
    file_glob: str | None = None,
    max_parallel: int | None = None,
) -> dict[str, object]:
    inputs = discover_inputs(config, file_glob=file_glob)
    manifest = {
        "include": [candidate.to_manifest_dict() for candidate in inputs],
        "count": len(inputs),
        "max_parallel": max_parallel or config.max_parallel_files,
        "fail_on_any_error": config.fail_on_any_error,
    }
    return manifest


def write_discovery_json(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
