from __future__ import annotations

import unittest

from stt.chunking import merge_chunk_texts, plan_chunks


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


if __name__ == "__main__":
    unittest.main()

