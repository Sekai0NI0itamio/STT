from __future__ import annotations

from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic
from typing import Any

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

    def transcribe(
        self,
        audio_path: Path,
        *,
        progress_logger: object | None = None,
        progress_label: str | None = None,
    ) -> TranscriptionResult:
        segments, info = self._model.transcribe(str(audio_path), beam_size=5)
        total_duration_seconds = _coerce_duration_seconds(getattr(info, "duration", None))
        progress_state = {"processed_seconds": 0.0}
        progress_lock = Lock()
        progress_stop = Event()
        progress_thread: Thread | None = None
        started_at = monotonic()

        if progress_logger is not None and total_duration_seconds and total_duration_seconds > 0:
            progress_thread = Thread(
                target=_log_transcription_progress,
                kwargs={
                    "logger": progress_logger,
                    "label": progress_label or audio_path.name,
                    "total_duration_seconds": total_duration_seconds,
                    "progress_state": progress_state,
                    "progress_lock": progress_lock,
                    "stop_event": progress_stop,
                    "started_at": started_at,
                },
                daemon=True,
            )
            progress_thread.start()

        collected_segments = []
        texts: list[str] = []
        try:
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
                segment_end = _coerce_duration_seconds(getattr(segment, "end", None))
                if segment_end is not None:
                    with progress_lock:
                        progress_state["processed_seconds"] = max(progress_state["processed_seconds"], segment_end)
        finally:
            progress_stop.set()
            if progress_thread is not None:
                progress_thread.join(timeout=2.0)

        if progress_logger is not None and total_duration_seconds and total_duration_seconds > 0:
            elapsed_seconds = max(monotonic() - started_at, 0.0)
            _emit_progress_log(
                logger=progress_logger,
                label=progress_label or audio_path.name,
                percent=100.0,
                elapsed_seconds=elapsed_seconds,
                eta_seconds=0.0,
            )

        return TranscriptionResult(
            text=" ".join(texts).strip(),
            language=getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            audio_duration_seconds=total_duration_seconds,
            segments=collected_segments,
        )


def _log_transcription_progress(
    *,
    logger: Any,
    label: str,
    total_duration_seconds: float,
    progress_state: dict[str, float],
    progress_lock: Lock,
    stop_event: Event,
    started_at: float,
) -> None:
    while not stop_event.wait(1.0):
        with progress_lock:
            processed_seconds = progress_state["processed_seconds"]
        elapsed_seconds = max(monotonic() - started_at, 0.001)
        percent = min((processed_seconds / total_duration_seconds) * 100.0, 99.9)
        eta_seconds = None
        if processed_seconds > 0.1:
            rate = processed_seconds / elapsed_seconds
            if rate > 0:
                eta_seconds = max((total_duration_seconds - processed_seconds) / rate, 0.0)
        _emit_progress_log(
            logger=logger,
            label=label,
            percent=percent,
            elapsed_seconds=elapsed_seconds,
            eta_seconds=eta_seconds,
        )


def _emit_progress_log(
    *,
    logger: Any,
    label: str,
    percent: float,
    elapsed_seconds: float,
    eta_seconds: float | None,
) -> None:
    eta_text = _format_duration(eta_seconds) if eta_seconds is not None else "estimating"
    logger.info(
        "Transcription progress %s %.1f%% elapsed=%s eta=%s",
        label,
        percent,
        _format_duration(elapsed_seconds),
        eta_text,
    )


def _coerce_duration_seconds(value: object) -> float | None:
    if value is None:
        return None
    try:
        duration_seconds = float(value)
    except (TypeError, ValueError):
        return None
    if duration_seconds <= 0:
        return None
    return duration_seconds


def _format_duration(value: float | None) -> str:
    if value is None:
        return "estimating"
    total_seconds = max(int(round(value)), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
