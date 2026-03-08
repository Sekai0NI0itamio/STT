from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .concurrency import parse_parallel_setting
from .config import load_config
from .discovery import build_discovery_manifest, write_discovery_json
from .pipeline import process_one_input
from .summarize import summarize_results
from .utils import write_github_outputs


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stt.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Discover committed MP3 inputs")
    _add_common_config_args(discover_parser)
    discover_parser.add_argument("--file-glob", default="")
    discover_parser.add_argument("--max-parallel", type=parse_parallel_setting)
    discover_parser.add_argument("--manifest-out")
    discover_parser.add_argument("--github-output-file")
    discover_parser.set_defaults(func=_run_discover)

    process_parser = subparsers.add_parser("process-one", help="Process one input audio file")
    _add_common_config_args(process_parser)
    process_parser.add_argument("--input-relpath", required=True)
    process_parser.add_argument("--job-output-dir", required=True)
    process_parser.set_defaults(func=_run_process_one)

    summarize_parser = subparsers.add_parser("summarize", help="Build run-level summaries")
    _add_common_config_args(summarize_parser)
    summarize_parser.add_argument("--results-root", required=True)
    summarize_parser.add_argument("--output-dir", required=True)
    summarize_parser.add_argument("--expected-count", type=int)
    summarize_parser.set_defaults(func=_run_summarize)
    return parser


def _add_common_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="stt.toml")
    parser.add_argument("--chunk-seconds", type=int)
    parser.add_argument("--chunk-target-seconds", type=int)
    parser.add_argument("--chunk-min-seconds", type=int)
    parser.add_argument("--chunk-workers", type=parse_parallel_setting)
    parser.add_argument("--model")
    parser.add_argument("--emit-chunk-debug")
    parser.add_argument("--fail-on-any-error")
    parser.add_argument("--max-input-mb", type=int)
    parser.add_argument("--max-parallel-files", type=parse_parallel_setting)


def _run_discover(args: argparse.Namespace) -> int:
    config = _load_config_from_args(args)
    manifest = build_discovery_manifest(
        config=config,
        file_glob=args.file_glob or None,
        max_parallel=args.max_parallel or config.max_parallel_files,
    )
    serialized = json.dumps(manifest, indent=2, sort_keys=True)
    print(serialized)
    if args.manifest_out:
        write_discovery_json(Path(args.manifest_out), manifest)
    if args.github_output_file:
        write_github_outputs(
            Path(args.github_output_file),
            {
                "matrix": {"include": manifest["include"]},
                "count": manifest["count"],
                "max_parallel": manifest["max_parallel"],
                "fail_on_any_error": config.fail_on_any_error,
            },
        )
    return 0


def _run_process_one(args: argparse.Namespace) -> int:
    config = _load_config_from_args(args)
    status = process_one_input(
        config=config,
        input_relpath=args.input_relpath,
        job_output_dir=Path(args.job_output_dir),
    )
    print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
    return 0 if status.status == "success" else 1


def _run_summarize(args: argparse.Namespace) -> int:
    config = _load_config_from_args(args)
    return summarize_results(
        config=config,
        results_root=Path(args.results_root),
        output_dir=Path(args.output_dir),
        expected_count=args.expected_count,
    )


def _load_config_from_args(args: argparse.Namespace):
    overrides = {
        "chunk_seconds": getattr(args, "chunk_seconds", None),
        "chunk_target_seconds": getattr(args, "chunk_target_seconds", None),
        "chunk_min_seconds": getattr(args, "chunk_min_seconds", None),
        "model": getattr(args, "model", None),
        "emit_chunk_debug": getattr(args, "emit_chunk_debug", None),
        "fail_on_any_error": getattr(args, "fail_on_any_error", None),
        "max_input_mb": getattr(args, "max_input_mb", None),
        "max_parallel_files": getattr(args, "max_parallel_files", None),
        "chunk_workers": getattr(args, "chunk_workers", None),
    }
    return load_config(args.config, overrides=overrides)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
