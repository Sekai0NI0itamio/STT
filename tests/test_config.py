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
                    max_input_mb = 40
                    chunk_seconds = 120
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
                    "emit_chunk_debug": "true",
                    "fail_on_any_error": "false",
                },
            )

            self.assertEqual(config.root_dir, root.resolve())
            self.assertEqual(config.incoming_dir, Path("audio"))
            self.assertEqual(config.outputs_dir, Path("artifacts"))
            self.assertEqual(config.chunk_seconds, 90)
            self.assertTrue(config.emit_chunk_debug)
            self.assertFalse(config.fail_on_any_error)
            self.assertEqual(config.max_input_bytes, 40 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()

