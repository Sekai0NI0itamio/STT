from __future__ import annotations

import unittest

from stt.concurrency import resolve_transcription_workers


class ConcurrencyTests(unittest.TestCase):
    def test_small_model_keeps_unlimited_chunk_parallelism(self) -> None:
        self.assertEqual(resolve_transcription_workers("small", task_count=21, cpu_count=4), 21)

    def test_medium_model_caps_transcription_workers_to_cpu_count(self) -> None:
        self.assertEqual(resolve_transcription_workers("medium", task_count=21, cpu_count=4), 4)

    def test_large_model_uses_more_conservative_cap(self) -> None:
        self.assertEqual(resolve_transcription_workers("large-v3", task_count=21, cpu_count=4), 2)


if __name__ == "__main__":
    unittest.main()
