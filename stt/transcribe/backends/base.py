from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ...models import TranscriptionResult


class TranscriptionBackend(Protocol):
    name: str

    def transcribe(
        self,
        audio_path: Path,
        *,
        progress_logger: object | None = None,
        progress_label: str | None = None,
    ) -> TranscriptionResult:
        """Return a transcript for the provided audio file."""
