from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
import traceback
from threading import BoundedSemaphore
from typing import Any
import shutil

from .backend_factory import build_backend
from .chunking import build_chunk_plans, merge_chunk_texts
from .concurrency import resolve_parallel_workers, resolve_transcription_workers
from .config import STTConfig
from .discovery import build_slug
from .ffmpeg_tools import FFmpegError, extract_chunk_mp3, normalize_audio, probe_duration_seconds
from .logging_utils import configure_file_logger
from .models import ChunkPlan, ChunkResult, PipelineStatus
from .utils import utcnow_iso, write_json, write_text


class PipelineStageError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def process_one_input(
    config: STTConfig,
    input_relpath: str,
    job_output_dir: Path,
) -> PipelineStatus:
    input_path = (config.root_dir / input_relpath).resolve()
    slug = build_slug(input_relpath)
    file_root = job_output_dir / slug
    work_root = file_root / "_work"
    log_path = file_root / "logs" / "process.log"
    logger = configure_file_logger(log_path)
    logger.info("Starting pipeline for %s", input_relpath)

    started_at = utcnow_iso()
    completed_at = started_at
    size_bytes = input_path.stat().st_size if input_path.exists() else 0
    chunk_results: list[ChunkResult] = []
    metadata: dict[str, Any] = {
        "input_relpath": input_relpath,
        "slug": slug,
        "config": config.to_dict(),
        "input": {
            "path": input_relpath,
            "exists": input_path.exists(),
            "size_bytes": size_bytes,
        },
        "artifacts": {
            "log_path": "logs/process.log",
        },
        "planned_chunks": [],
        "chunk_results": [],
    }
    transcript_chars = 0
    transcript_path: str | None = None
    audio_duration_seconds: float | None = None
    failure_stage: str | None = None
    failure_message: str | None = None

    try:
        _validate_input(config, input_path)

        if config.transcription_mode == "direct":
            logger.info(
                "Using direct transcription mode for %s; skipping normalization and chunk export",
                input_relpath,
            )
            chunk_plan, chunk_results, chunking_metadata = _process_direct_transcription(
                config=config,
                input_path=input_path,
                file_root=file_root,
                logger=logger,
            )
        else:
            chunk_plan, chunk_results, chunking_metadata, audio_duration_seconds = _process_chunked_transcription(
                config=config,
                input_path=input_path,
                file_root=file_root,
                work_root=work_root,
                logger=logger,
            )
            metadata["normalized_audio"] = {
                "duration_seconds": audio_duration_seconds,
                "sample_rate_hz": config.sample_rate_hz,
                "audio_channels": config.audio_channels,
                "retained_in_artifact": False,
            }

        if audio_duration_seconds is None and chunk_results:
            audio_duration_seconds = chunk_results[0].duration_seconds or None
        metadata["transcription_mode"] = config.transcription_mode

        metadata["planned_chunks"] = [chunk.to_dict() for chunk in chunk_plan]
        metadata["chunking"] = chunking_metadata
        metadata["chunk_results"] = [_serialize_chunk_result(result, config.emit_chunk_debug) for result in chunk_results]
        write_json(file_root / "chunks" / "chunk-manifest.json", metadata["chunk_results"])

        for result in chunk_results:
            if result.status == "success":
                if result.audio_size_bytes > 0:
                    logger.info(
                        "Completed chunk %s audio_size_bytes=%d",
                        result.chunk_id,
                        result.audio_size_bytes,
                    )
                else:
                    logger.info("Completed chunk %s", result.chunk_id)
            else:
                logger.error("Chunk %s failed: %s", result.chunk_id, result.error_message)
                if failure_stage is None:
                    failure_stage = result.error_stage or "transcription"
                    failure_message = f"{result.chunk_id}: {result.error_message}"

        if any(result.status != "success" for result in chunk_results):
            raise PipelineStageError(
                "transcription",
                "One or more transcription units failed. See chunk-manifest.json and logs/process.log for details.",
            )

        final_transcript = merge_chunk_texts([result.transcript_text for result in chunk_results])
        transcript_path = "transcript.txt"
        transcript_chars = len(final_transcript)
        write_text(file_root / transcript_path, final_transcript + "\n")
        logger.info("Wrote final transcript to %s", transcript_path)

        status_value = "success"
    except PipelineStageError as exc:
        logger.error("%s failure: %s", exc.stage, exc)
        if failure_stage is None:
            failure_stage = exc.stage
            failure_message = str(exc)
        status_value = "failed"
    except FFmpegError as exc:
        logger.error("ffmpeg failure: %s", exc)
        failure_stage = failure_stage or "normalization"
        failure_message = failure_message or str(exc)
        status_value = "failed"
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected failure: %s", exc)
        logger.error("Traceback:\n%s", traceback.format_exc())
        failure_stage = failure_stage or "pipeline"
        failure_message = failure_message or str(exc)
        status_value = "failed"
    finally:
        completed_at = utcnow_iso()
        if work_root.exists():
            shutil.rmtree(work_root, ignore_errors=True)

    status = PipelineStatus(
        input_relpath=input_relpath,
        slug=slug,
        status=status_value,
        size_bytes=size_bytes,
        backend=config.backend,
        model=config.model,
        started_at=started_at,
        completed_at=completed_at,
        audio_duration_seconds=audio_duration_seconds,
        chunks_total=len(chunk_results),
        chunks_succeeded=sum(1 for result in chunk_results if result.status == "success"),
        transcript_path=transcript_path,
        transcript_chars=transcript_chars,
        failure_stage=failure_stage,
        failure_message=failure_message,
    )

    metadata["status"] = status.to_dict()
    write_json(file_root / "metadata.json", metadata)
    write_json(file_root / "status.json", status.to_dict())
    logger.info("Completed pipeline for %s with status=%s", input_relpath, status.status)
    return status


def _validate_input(config: STTConfig, input_path: Path) -> None:
    if not input_path.exists():
        raise PipelineStageError("input_validation", f"Input file does not exist: {input_path}")
    if input_path.suffix.lower() != ".mp3":
        raise PipelineStageError("input_validation", f"Only .mp3 files are supported: {input_path}")


def _process_direct_transcription(
    *,
    config: STTConfig,
    input_path: Path,
    file_root: Path,
    logger: Any,
) -> tuple[list[ChunkPlan], list[ChunkResult], dict[str, Any]]:
    direct_chunk = ChunkPlan(
        chunk_id="full-input",
        index=0,
        start_seconds=0.0,
        duration_seconds=0.0,
    )
    chunking_metadata = {
        "strategy": "direct-full-input",
        "configured_chunk_workers": config.chunk_workers,
        "resolved_chunk_workers": 1,
        "resolved_transcription_workers": 1,
    }

    try:
        logger.info("Submitting full-input duration=full-file")
        backend = _initialize_backend(config, 1, logger)
        transcription = backend.transcribe(
            input_path,
            progress_logger=logger,
            progress_label="full-input",
        )
        duration_seconds = (
            transcription.audio_duration_seconds
            or _max_segment_end_seconds(transcription.segments)
            or probe_duration_seconds(input_path)
        )
        direct_chunk = ChunkPlan(
            chunk_id="full-input",
            index=0,
            start_seconds=0.0,
            duration_seconds=round(duration_seconds, 3),
        )
        chunking_metadata["duration_ms"] = int(round(duration_seconds * 1000))
        text = transcription.text.strip()
        transcript_debug_path = None
        debug_path = None
        if config.emit_chunk_debug:
            transcript_debug_path = "chunks/full-input.txt"
            debug_path = "chunks/full-input.json"
            write_text(file_root / transcript_debug_path, text)
            write_json(file_root / debug_path, transcription.to_dict())
        return (
            [direct_chunk],
            [
                ChunkResult(
                    chunk_id=direct_chunk.chunk_id,
                    index=direct_chunk.index,
                    start_seconds=direct_chunk.start_seconds,
                    duration_seconds=direct_chunk.duration_seconds,
                    status="success",
                    transcript_text=text,
                    transcript_path=transcript_debug_path,
                    language=transcription.language,
                    language_probability=transcription.language_probability,
                    segment_count=len(transcription.segments),
                    debug_path=debug_path,
                )
            ],
            chunking_metadata,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Direct transcription failed")
        return (
            [direct_chunk],
            [
                ChunkResult(
                    chunk_id=direct_chunk.chunk_id,
                    index=direct_chunk.index,
                    start_seconds=direct_chunk.start_seconds,
                    duration_seconds=direct_chunk.duration_seconds,
                    status="failed",
                    error_stage=_classify_chunk_error(exc),
                    error_message=str(exc),
                )
            ],
            chunking_metadata,
        )


def _process_chunked_transcription(
    *,
    config: STTConfig,
    input_path: Path,
    file_root: Path,
    work_root: Path,
    logger: Any,
) -> tuple[list[ChunkPlan], list[ChunkResult], dict[str, Any], float]:
    normalized_path = work_root / "normalized" / "audio.wav"
    logger.info("Normalizing audio to %s", normalized_path)
    normalize_audio(
        input_path=input_path,
        output_path=normalized_path,
        sample_rate_hz=config.sample_rate_hz,
        audio_channels=config.audio_channels,
    )

    audio_duration_seconds = probe_duration_seconds(normalized_path)
    chunk_plan, chunking_metadata = build_chunk_plans(normalized_path, config)
    resolved_chunk_workers = resolve_parallel_workers(config.chunk_workers, len(chunk_plan))
    resolved_transcription_workers = resolve_transcription_workers(config.model, len(chunk_plan))
    chunking_metadata = {
        **chunking_metadata,
        "configured_chunk_workers": config.chunk_workers,
        "resolved_chunk_workers": resolved_chunk_workers,
        "resolved_transcription_workers": resolved_transcription_workers,
    }
    logger.info(
        (
            "Chunking produced %d chunk(s) with max_chunk_duration_ms=%s, "
            "chunk_workers=%d, transcription_workers=%d"
        ),
        len(chunk_plan),
        chunking_metadata["max_chunk_duration_ms"],
        resolved_chunk_workers,
        resolved_transcription_workers,
    )

    chunk_results: list[ChunkResult] = []
    transcription_gate = BoundedSemaphore(value=resolved_transcription_workers)
    with ThreadPoolExecutor(
        max_workers=resolved_chunk_workers + 1,
        thread_name_prefix="stt-chunk",
    ) as executor:
        backend_future = executor.submit(
            _initialize_backend,
            config,
            resolved_transcription_workers,
            logger,
        )
        futures = {
            executor.submit(
                _process_chunk,
                chunk=chunk,
                normalized_path=normalized_path,
                file_root=file_root,
                work_root=work_root,
                config=config,
                backend_future=backend_future,
                transcription_gate=transcription_gate,
                logger=logger,
            ): chunk
            for chunk in chunk_plan
        }
        for future in as_completed(futures):
            chunk_results.append(future.result())

    chunk_results.sort(key=lambda result: result.index)
    return chunk_plan, chunk_results, chunking_metadata, audio_duration_seconds


def _process_chunk(
    *,
    chunk: ChunkPlan,
    normalized_path: Path,
    file_root: Path,
    work_root: Path,
    config: STTConfig,
    backend_future: Future[Any],
    transcription_gate: BoundedSemaphore,
    logger: Any,
) -> ChunkResult:
    chunk_audio_path = work_root / "chunks" / f"{chunk.chunk_id}.mp3"
    retained_chunk_audio_path = None
    logger.info(
        "Submitting chunk %s start=%.3fs duration=%.3fs",
        chunk.chunk_id,
        chunk.start_seconds,
        chunk.duration_seconds,
    )
    try:
        extract_chunk_mp3(
            input_path=normalized_path,
            output_path=chunk_audio_path,
            start_seconds=chunk.start_seconds,
            duration_seconds=chunk.duration_seconds,
            sample_rate_hz=config.sample_rate_hz,
            audio_channels=config.audio_channels,
            bitrate_kbps=config.chunk_bitrate_kbps,
        )
        audio_size_bytes = chunk_audio_path.stat().st_size
        if audio_size_bytes > config.max_input_bytes:
            raise PipelineStageError(
                "chunking",
                (
                    f"{chunk.chunk_id} exceeded max_input_mb={config.max_input_mb} "
                    f"after export: {audio_size_bytes} bytes"
                ),
            )
        if config.emit_chunk_debug:
            retained_chunk_audio_path = f"chunks/{chunk.chunk_id}.mp3"
            shutil.copy2(chunk_audio_path, file_root / retained_chunk_audio_path)
        backend = backend_future.result()
        transcription_gate.acquire()
        try:
            transcription = backend.transcribe(chunk_audio_path)
        finally:
            transcription_gate.release()
        text = transcription.text.strip()
        transcript_debug_path = None
        debug_path = None
        if config.emit_chunk_debug:
            transcript_debug_path = f"chunks/{chunk.chunk_id}.txt"
            debug_path = f"chunks/{chunk.chunk_id}.json"
            write_text(file_root / transcript_debug_path, text)
            write_json(file_root / debug_path, transcription.to_dict())
        return ChunkResult(
            chunk_id=chunk.chunk_id,
            index=chunk.index,
            start_seconds=chunk.start_seconds,
            duration_seconds=chunk.duration_seconds,
            status="success",
            audio_path=retained_chunk_audio_path,
            audio_size_bytes=audio_size_bytes,
            transcript_text=text,
            transcript_path=transcript_debug_path,
            language=transcription.language,
            language_probability=transcription.language_probability,
            segment_count=len(transcription.segments),
            debug_path=debug_path,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chunk %s failed inside worker", chunk.chunk_id)
        return ChunkResult(
            chunk_id=chunk.chunk_id,
            index=chunk.index,
            start_seconds=chunk.start_seconds,
            duration_seconds=chunk.duration_seconds,
            status="failed",
            audio_path=retained_chunk_audio_path,
            audio_size_bytes=chunk_audio_path.stat().st_size if chunk_audio_path.exists() else 0,
            error_stage=_classify_chunk_error(exc),
            error_message=str(exc),
        )
    finally:
        if chunk_audio_path.exists():
            chunk_audio_path.unlink()


def _classify_chunk_error(exc: Exception) -> str:
    if isinstance(exc, PipelineStageError):
        return exc.stage
    if isinstance(exc, FFmpegError):
        return "chunking"
    return "transcription"


def _initialize_backend(config: STTConfig, resolved_transcription_workers: int, logger: Any) -> Any:
    logger.info(
        "Starting backend initialization: backend=%s model=%s transcription_workers=%d",
        config.backend,
        config.model,
        resolved_transcription_workers,
    )
    backend = build_backend(config, num_workers=resolved_transcription_workers)
    logger.info("Loaded backend=%s model=%s", config.backend, config.model)
    return backend


def _serialize_chunk_result(result: ChunkResult, include_text: bool) -> dict[str, Any]:
    payload = result.to_dict()
    if not include_text:
        payload.pop("transcript_text", None)
    return payload


def _max_segment_end_seconds(segments: list[dict[str, Any]]) -> float | None:
    max_end = 0.0
    for segment in segments:
        try:
            segment_end = float(segment.get("end", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if segment_end > max_end:
            max_end = segment_end
    return max_end or None
