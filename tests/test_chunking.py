from __future__ import annotations

import unittest

from stt.chunking import (
    expand_ranges,
    group_ranges_into_chunks,
    max_chunk_duration_ms,
    merge_chunk_texts,
    plan_chunks,
)


class ChunkingTests(unittest.TestCase):
    def test_plan_chunks_covers_full_duration(self) -> None:
        chunks = plan_chunks(duration_seconds=610.0, chunk_seconds=300)
        self.assertEqual([chunk.duration_seconds for chunk in chunks], [300.0, 300.0, 10.0])
        self.assertEqual(chunks[0].start_seconds, 0.0)
        self.assertEqual(chunks[1].start_seconds, 300.0)
        self.assertEqual(chunks[2].start_seconds, 600.0)

    def test_merge_chunk_texts_preserves_order_and_strips_noise(self) -> None:
        merged = merge_chunk_texts(["  hello world  ", "", "second chunk", "   "])
        self.assertEqual(merged, "hello world\n\nsecond chunk")

    def test_size_cap_duration_uses_bitrate_and_margin(self) -> None:
        duration_ms = max_chunk_duration_ms(
            max_chunk_bytes=25 * 1024 * 1024,
            bitrate_kbps=64,
            safety_margin=0.9,
        )
        self.assertGreater(duration_ms, 2_900_000)
        self.assertLess(duration_ms, 3_000_000)

    def test_group_ranges_prefers_silence_boundaries_and_splits_long_ranges(self) -> None:
        expanded = expand_ranges(
            speech_ranges_ms=[(1_000, 2_000), (2_400, 3_500), (8_000, 15_500)],
            total_duration_ms=16_000,
            keep_silence_ms=250,
        )
        self.assertEqual(expanded, [(750, 3750), (7750, 15750)])

        chunks = group_ranges_into_chunks(
            speech_ranges_ms=expanded,
            total_duration_ms=16_000,
            max_chunk_duration_ms=4_000,
        )
        self.assertEqual(chunks, [(750, 3750), (7750, 11750), (11750, 15750)])


if __name__ == "__main__":
    unittest.main()
