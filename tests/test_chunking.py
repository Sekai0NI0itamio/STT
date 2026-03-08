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
        chunks = plan_chunks(duration_seconds=610.0, chunk_seconds=60)
        self.assertEqual([chunk.duration_seconds for chunk in chunks], [60.0] * 10 + [10.0])
        self.assertEqual(chunks[0].start_seconds, 0.0)
        self.assertEqual(chunks[1].start_seconds, 60.0)
        self.assertEqual(chunks[-1].start_seconds, 600.0)

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

    def test_group_ranges_prefers_30_to_60_second_silence_boundaries(self) -> None:
        expanded = expand_ranges(
            speech_ranges_ms=[
                (0, 18_000),
                (20_000, 42_000),
                (45_000, 69_000),
                (75_000, 92_000),
            ],
            total_duration_ms=95_000,
            keep_silence_ms=250,
        )
        self.assertEqual(expanded, [(0, 18250), (19750, 42250), (44750, 69250), (74750, 92250)])

        chunks = group_ranges_into_chunks(
            speech_ranges_ms=expanded,
            total_duration_ms=95_000,
            target_chunk_duration_ms=45_000,
            max_chunk_duration_ms=60_000,
            min_chunk_duration_ms=30_000,
        )
        self.assertEqual(chunks, [(0, 42250), (44750, 92250)])

    def test_group_ranges_evenly_splits_single_long_range_when_no_cut_exists(self) -> None:
        chunks = group_ranges_into_chunks(
            speech_ranges_ms=[(0, 170_000)],
            total_duration_ms=170_000,
            target_chunk_duration_ms=45_000,
            max_chunk_duration_ms=60_000,
            min_chunk_duration_ms=30_000,
        )
        self.assertEqual(chunks, [(0, 42500), (42500, 85000), (85000, 127500), (127500, 170000)])


if __name__ == "__main__":
    unittest.main()
