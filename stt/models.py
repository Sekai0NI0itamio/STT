from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class InputCandidate:
    relpath: str
    abs_path: Path
    size_bytes: int
    slug: str
    validation_errors: list[str] = field(default_factory=list)

    @property
    def artifact_name(self) -> str:
        return f"stt-file-{self.slug}"

    @property
    def is_valid(self) -> bool:
        return not self.validation_errors

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "relpath": self.relpath,
            "size_bytes": self.size_bytes,
            "slug": self.slug,
            "validation_errors": list(self.validation_errors),
            "artifact_name": self.artifact_name,
        }


@dataclass(slots=True)
class ChunkPlan:
    chunk_id: str
    index: int
    start_seconds: float
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChunkResult:
    chunk_id: str
    index: int
    start_seconds: float
    duration_seconds: float
    status: str
    audio_path: str | None = None
    audio_size_bytes: int = 0
    transcript_text: str = ""
    transcript_path: str | None = None
    error_stage: str | None = None
    error_message: str | None = None
    language: str | None = None
    language_probability: float | None = None
    segment_count: int = 0
    debug_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PipelineStatus:
    input_relpath: str
    slug: str
    status: str
    size_bytes: int
    backend: str
    model: str
    started_at: str
    completed_at: str
    audio_duration_seconds: float | None = None
    chunks_total: int = 0
    chunks_succeeded: int = 0
    transcript_path: str | None = None
    transcript_chars: int = 0
    failure_stage: str | None = None
    failure_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    language: str | None = None
    language_probability: float | None = None
    segments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
