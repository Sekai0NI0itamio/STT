from __future__ import annotations

from pathlib import Path
import traceback
from typing import Any
import shutil

from .backend_factory import build_backend
from .chunking import merge_chunk_texts, plan_chunks
from .config import STTConfig
from .discovery import build_slug
from .ffmpeg_tools import FFmpegError, extract_chunk, normalize_audio, probe_duration_seconds
from .logging_utils import configure_file_logger
from .models import ChunkResult, PipelineStatus
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

        normalized_path = work_root / "normalized" / "audio.wav"
        logger.info("Normalizing audio to %s", normalized_path)
        normalize_audio(
            input_path=input_path,
            output_path=normalized_path,
            sample_rate_hz=config.sample_rate_hz,
            audio_channels=config.audio_channels,
        )

        audio_duration_seconds = probe_duration_seconds(normalized_path)
        metadata["normalized_audio"] = {
            "duration_seconds": audio_duration_seconds,
            "sample_rate_hz": config.sample_rate_hz,
            "audio_channels": config.audio_channels,
            "retained_in_artifact": False,
        }

        chunk_plan = plan_chunks(audio_duration_seconds, config.chunk_seconds)
        metadata["planned_chunks"] = [chunk.to_dict() for chunk in chunk_plan]
        backend = build_backend(config)
        logger.info("Loaded backend=%s model=%s", config.backend, config.model)

        for chunk in chunk_plan:
            chunk_audio_path = work_root / "chunks" / f"{chunk.chunk_id}.wav"
            logger.info(
                "Processing chunk %s start=%.3fs duration=%.3fs",
                chunk.chunk_id,
                chunk.start_seconds,
                chunk.duration_seconds,
            )
            try:
                extract_chunk(
                    input_path=normalized_path,
                    output_path=chunk_audio_path,
                    start_seconds=chunk.start_seconds,
                    duration_seconds=chunk.duration_seconds,
                )
                transcription = backend.transcribe(chunk_audio_path)
                text = transcription.text.strip()
                transcript_debug_path = None
                debug_path = None
                if config.emit_chunk_debug:
                    transcript_debug_path = f"chunks/{chunk.chunk_id}.txt"
                    debug_path = f"chunks/{chunk.chunk_id}.json"
                    write_text(file_root / transcript_debug_path, text)
                    write_json(file_root / debug_path, transcription.to_dict())
                chunk_results.append(
                    ChunkResult(
                        chunk_id=chunk.chunk_id,
                        index=chunk.index,
                        start_seconds=chunk.start_seconds,
                        duration_seconds=chunk.duration_seconds,
                        status="success",
                        transcript_text=text,
                        transcript_path=transcript_debug_path,
                        language=transcription.language,
                        language_probability=transcription.language_probability,
                        segment_count=len(transcription.segments),
                        debug_path=debug_path,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Chunk %s failed", chunk.chunk_id)
                if failure_stage is None:
                    failure_stage = "chunking" if isinstance(exc, FFmpegError) else "transcription"
                    failure_message = f"{chunk.chunk_id}: {exc}"
                chunk_results.append(
                    ChunkResult(
                        chunk_id=chunk.chunk_id,
                        index=chunk.index,
                        start_seconds=chunk.start_seconds,
                        duration_seconds=chunk.duration_seconds,
                        status="failed",
                        error_message=str(exc),
                    )
                )
                continue
            finally:
                if chunk_audio_path.exists():
                    chunk_audio_path.unlink()

        metadata["chunk_results"] = [_serialize_chunk_result(result, config.emit_chunk_debug) for result in chunk_results]
        write_json(file_root / "chunks" / "chunk-manifest.json", metadata["chunk_results"])

        if any(result.status != "success" for result in chunk_results):
            raise PipelineStageError(
                "transcription",
                "One or more chunks failed. See chunk-manifest.json and logs/process.log for details.",
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
    size_bytes = input_path.stat().st_size
    if size_bytes > config.max_input_bytes:
        raise PipelineStageError(
            "input_validation",
            f"Input file exceeds max_input_mb={config.max_input_mb}: {size_bytes} bytes",
        )


def _serialize_chunk_result(result: ChunkResult, include_text: bool) -> dict[str, Any]:
    payload = result.to_dict()
    if not include_text:
        payload.pop("transcript_text", None)
    return payload
