from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from stt.config import load_config
from stt.summarize import summarize_results


class SummaryTests(unittest.TestCase):
    def test_summary_generation_with_mixed_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_root = root / "results"
            output_dir = root / "summary"
            config_path = root / "stt.toml"
            config_path.write_text(
                "incoming_dir = \"incoming\"\noutputs_dir = \"outputs\"\nfail_on_any_error = true\n",
                encoding="utf-8",
            )

            success_dir = results_root / "file-a"
            success_dir.mkdir(parents=True)
            (success_dir / "status.json").write_text(
                json.dumps(
                    {
                        "input_relpath": "incoming/a.mp3",
                        "slug": "file-a",
                        "status": "success",
                        "size_bytes": 10,
                        "backend": "faster-whisper",
                        "model": "small",
                        "started_at": "2026-03-08T00:00:00+00:00",
                        "completed_at": "2026-03-08T00:01:00+00:00",
                        "audio_duration_seconds": 12.3,
                        "chunks_total": 1,
                        "chunks_succeeded": 1,
                        "transcript_path": "transcript.txt",
                        "transcript_chars": 0,
                        "failure_stage": None,
                        "failure_message": None,
                    }
                ),
                encoding="utf-8",
            )
            (success_dir / "transcript.txt").write_text("hello from file a\n", encoding="utf-8")

            failed_dir = results_root / "file-b"
            failed_dir.mkdir(parents=True)
            (failed_dir / "status.json").write_text(
                json.dumps(
                    {
                        "input_relpath": "incoming/b.mp3",
                        "slug": "file-b",
                        "status": "failed",
                        "size_bytes": 12,
                        "backend": "faster-whisper",
                        "model": "small",
                        "started_at": "2026-03-08T00:00:00+00:00",
                        "completed_at": "2026-03-08T00:01:00+00:00",
                        "audio_duration_seconds": 20.0,
                        "chunks_total": 2,
                        "chunks_succeeded": 1,
                        "transcript_path": None,
                        "transcript_chars": 0,
                        "failure_stage": "transcription",
                        "failure_message": "chunk-0001: backend error",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)
            exit_code = summarize_results(config, results_root, output_dir, expected_count=2)

            self.assertEqual(exit_code, 1)
            summary_json = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary_json["totals"]["successes"], 1)
            self.assertEqual(summary_json["totals"]["failures"], 1)

            combined = (output_dir / "combined-transcript.txt").read_text(encoding="utf-8")
            self.assertIn("===== incoming/a.mp3 =====", combined)
            self.assertIn("hello from file a", combined)
            self.assertIn("===== incoming/b.mp3 =====", combined)
            self.assertIn("[TRANSCRIPT MISSING] stage=transcription; message=chunk-0001: backend error", combined)


if __name__ == "__main__":
    unittest.main()
