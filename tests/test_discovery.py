from __future__ import annotations

import tempfile
from pathlib import Path
import textwrap
import unittest

from stt.config import load_config
from stt.discovery import discover_inputs


class DiscoveryTests(unittest.TestCase):
    def test_recursive_discovery_without_rejecting_large_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "incoming" / "nested").mkdir(parents=True)
            (root / "incoming" / "b.mp3").write_bytes(b"a")
            (root / "incoming" / "nested" / "a.MP3").write_bytes(b"b")
            (root / "incoming" / "skip.txt").write_text("ignore", encoding="utf-8")
            (root / "incoming" / "too-big.mp3").write_bytes(b"x" * (1024 * 1024 + 1))
            (root / "stt.toml").write_text(
                textwrap.dedent(
                    """
                    incoming_dir = "incoming"
                    outputs_dir = "outputs"
                    max_input_mb = 1
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_config(root / "stt.toml")
            discovered = discover_inputs(config)

            self.assertEqual(
                [candidate.relpath for candidate in discovered],
                [
                    "incoming/b.mp3",
                    "incoming/nested/a.MP3",
                    "incoming/too-big.mp3",
                ],
            )
            oversize = next(candidate for candidate in discovered if candidate.relpath.endswith("too-big.mp3"))
            self.assertTrue(oversize.is_valid)
            self.assertEqual(oversize.validation_errors, [])

            filtered = discover_inputs(config, file_glob="incoming/nested/*")
            self.assertEqual([candidate.relpath for candidate in filtered], ["incoming/nested/a.MP3"])

            recursive = discover_inputs(config, file_glob="incoming/**/*.mp3")
            self.assertEqual(
                [candidate.relpath for candidate in recursive],
                [
                    "incoming/b.mp3",
                    "incoming/nested/a.MP3",
                    "incoming/too-big.mp3",
                ],
            )


if __name__ == "__main__":
    unittest.main()
