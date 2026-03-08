from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ...models import TranscriptionResult


class TranscriptionBackend(Protocol):
    name: str

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Return a transcript for the provided audio file."""

