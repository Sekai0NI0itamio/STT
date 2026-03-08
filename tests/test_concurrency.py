from __future__ import annotations

import unittest

from stt.concurrency import parse_parallel_setting, resolve_parallel_workers


class ConcurrencyTests(unittest.TestCase):
    def test_parse_parallel_setting_supports_unlimited(self) -> None:
        self.assertEqual(parse_parallel_setting("unlimited"), 0)
        self.assertEqual(parse_parallel_setting("auto"), 0)
        self.assertEqual(parse_parallel_setting(4), 4)

    def test_resolve_parallel_workers_uses_all_tasks_when_unlimited(self) -> None:
        self.assertEqual(resolve_parallel_workers(0, 5), 5)
        self.assertEqual(resolve_parallel_workers(2, 5), 2)
        self.assertEqual(resolve_parallel_workers(10, 3), 3)
        self.assertEqual(resolve_parallel_workers(0, 0), 1)
