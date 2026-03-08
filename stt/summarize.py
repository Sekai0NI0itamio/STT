from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from .config import STTConfig
from .utils import append_text, read_json, utcnow_iso, write_json, write_text


def summarize_results(
    config: STTConfig,
    results_root: Path,
    output_dir: Path,
    expected_count: int | None = None,
) -> int:
    records = load_result_records(results_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    totals = {
        "files": len(records),
        "successes": sum(1 for record in records if record["status"] == "success"),
        "failures": sum(1 for record in records if record["status"] != "success"),
        "expected_files": expected_count,
        "missing_results": max((expected_count or len(records)) - len(records), 0),
    }

    summary = {
        "generated_at": utcnow_iso(),
        "config": config.to_dict(),
        "totals": totals,
        "files": records,
    }
    summary_markdown = build_summary_markdown(records, totals)
    combined_transcript = build_combined_transcript(records)

    write_json(output_dir / "summary.json", summary)
    write_text(output_dir / "summary.md", summary_markdown)
    write_text(output_dir / "combined-transcript.txt", combined_transcript)

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        append_text(Path(step_summary_path), summary_markdown + "\n")

    should_fail = totals["files"] == 0 or (
        config.fail_on_any_error and (totals["failures"] > 0 or totals["missing_results"] > 0)
    )
    return 1 if should_fail else 0


def load_result_records(results_root: Path) -> list[dict[str, Any]]:
    status_files = sorted(results_root.rglob("status.json"))
    records: list[dict[str, Any]] = []
    for status_path in status_files:
        status = read_json(status_path)
        result_dir = status_path.parent
        transcript_path = result_dir / "transcript.txt"
        if transcript_path.exists():
            transcript_text = transcript_path.read_text(encoding="utf-8").strip()
            status["transcript_text"] = transcript_text
            status["transcript_chars"] = len(transcript_text)
        else:
            status["transcript_text"] = ""
            status["transcript_chars"] = int(status.get("transcript_chars", 0) or 0)
        records.append(status)

    return sorted(records, key=lambda record: record["input_relpath"])


def build_summary_markdown(records: list[dict[str, Any]], totals: dict[str, Any]) -> str:
    lines = [
        "# STT Run Summary",
        "",
        f"- Files discovered: {totals['expected_files'] if totals['expected_files'] is not None else totals['files']}",
        f"- Files summarized: {totals['files']}",
        f"- Successes: {totals['successes']}",
        f"- Failures: {totals['failures']}",
    ]
    if totals["missing_results"]:
        lines.append(f"- Missing result folders: {totals['missing_results']}")
    lines.extend(
        [
            "",
            "| Input file | Status | Duration (s) | Chunks | Transcript chars | Failure |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for record in records:
        duration = _format_float(record.get("audio_duration_seconds"))
        failure = "-"
        if record["status"] != "success":
            stage = record.get("failure_stage") or "unknown"
            message = record.get("failure_message") or "No message"
            failure = f"{stage}: {message}"
        lines.append(
            "| {input_relpath} | {status} | {duration} | {chunks_succeeded}/{chunks_total} | "
            "{transcript_chars} | {failure} |".format(
                input_relpath=record["input_relpath"],
                status=record["status"],
                duration=duration,
                chunks_succeeded=record.get("chunks_succeeded", 0),
                chunks_total=record.get("chunks_total", 0),
                transcript_chars=record.get("transcript_chars", 0),
                failure=failure.replace("\n", " ").replace("|", "/"),
            )
        )
    return "\n".join(lines)


def build_combined_transcript(records: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for record in records:
        header = f"===== {record['input_relpath']} ====="
        if record["status"] == "success":
            body = record.get("transcript_text", "").strip() or "[TRANSCRIPT EMPTY]"
        else:
            stage = record.get("failure_stage") or "unknown"
            message = record.get("failure_message") or "No message recorded."
            body = f"[TRANSCRIPT MISSING] stage={stage}; message={message}"
        sections.append(f"{header}\n{body}".strip())
    return "\n\n".join(sections).strip() + ("\n" if sections else "")


def _format_float(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}"

