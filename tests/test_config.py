from __future__ import annotations

import tempfile
from pathlib import Path
import textwrap
import unittest

from stt.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_and_apply_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "stt.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    incoming_dir = "audio"
                    outputs_dir = "artifacts"
                    transcription_mode = "chunked"
                    max_input_mb = 40
                    chunk_seconds = 60
                    chunk_target_seconds = 45
                    chunk_min_seconds = 30
                    chunk_bitrate_kbps = 48
                    min_silence_len_ms = 700
                    silence_thresh_dbfs = -35
                    keep_silence_ms = 250
                    chunk_size_safety_margin = 0.8
                    max_parallel_files = "unlimited"
                    chunk_workers = 4
                    model = "base"
                    emit_chunk_debug = false
                    fail_on_any_error = true
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_config(
                config_path,
                overrides={
                    "chunk_seconds": 90,
                    "transcription_mode": "direct",
                    "chunk_target_seconds": 40,
                    "chunk_min_seconds": 25,
                    "emit_chunk_debug": "true",
                    "fail_on_any_error": "false",
                    "chunk_workers": "unlimited",
                },
            )

            self.assertEqual(config.root_dir, root.resolve())
            self.assertEqual(config.incoming_dir, Path("audio"))
            self.assertEqual(config.outputs_dir, Path("artifacts"))
            self.assertEqual(config.transcription_mode, "direct")
            self.assertEqual(config.chunk_seconds, 90)
            self.assertEqual(config.chunk_target_seconds, 40)
            self.assertEqual(config.chunk_min_seconds, 25)
            self.assertEqual(config.chunk_bitrate_kbps, 48)
            self.assertEqual(config.min_silence_len_ms, 700)
            self.assertEqual(config.silence_thresh_dbfs, -35)
            self.assertEqual(config.keep_silence_ms, 250)
            self.assertEqual(config.chunk_size_safety_margin, 0.8)
            self.assertEqual(config.max_parallel_files, 0)
            self.assertEqual(config.chunk_workers, 0)
            self.assertTrue(config.emit_chunk_debug)
            self.assertFalse(config.fail_on_any_error)
            self.assertEqual(config.max_input_bytes, 40 * 1024 * 1024)

    def test_invalid_transcription_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "stt.toml"
            config_path.write_text('transcription_mode = "invalid"\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "transcription_mode"):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()
