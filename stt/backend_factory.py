from __future__ import annotations

from .config import STTConfig
from .transcribe.backends.base import TranscriptionBackend
from .transcribe.backends.faster_whisper_backend import FasterWhisperBackend


def build_backend(config: STTConfig) -> TranscriptionBackend:
    if config.backend == "faster-whisper":
        return FasterWhisperBackend(config)
    raise ValueError(f"Unsupported backend: {config.backend}")
