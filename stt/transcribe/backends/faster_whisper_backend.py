from __future__ import annotations

from pathlib import Path

from ...config import STTConfig
from ...models import TranscriptionResult


class FasterWhisperBackend:
    name = "faster-whisper"

    def __init__(self, config: STTConfig, num_workers: int | None = None) -> None:
        self._config = config
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Install the runtime extras before transcribing."
            ) from exc

        self._model = WhisperModel(
            config.model,
            device="cpu",
            compute_type="int8",
            num_workers=max(int(num_workers or 1), 1),
        )

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        segments, info = self._model.transcribe(str(audio_path), beam_size=5)
        collected_segments = []
        texts: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                texts.append(text)
            collected_segments.append(
                {
                    "id": getattr(segment, "id", None),
                    "start": getattr(segment, "start", None),
                    "end": getattr(segment, "end", None),
                    "text": text,
                }
            )

        return TranscriptionResult(
            text=" ".join(texts).strip(),
            language=getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            segments=collected_segments,
        )
