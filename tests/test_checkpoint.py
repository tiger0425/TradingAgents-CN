"""Test V1.2 checkpoint support: get_checkpointer works, thread_id determinism."""

import tempfile
import unittest

from tradingagents.graph.checkpointer import (
    clear_checkpoint_for_task,
    get_checkpointer,
    get_checkpointer_for_task,
    thread_id,
    thread_id_for_task,
)


class TestCheckpointerBasics(unittest.TestCase):
    def test_get_checkpointer_works(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with get_checkpointer(tmpdir, "TEST") as saver:
                self.assertIsNotNone(saver)
                self.assertTrue(hasattr(saver, "get_tuple"))

    def test_get_checkpointer_for_task_works(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with get_checkpointer_for_task(tmpdir, "600519:alice:scheduled") as saver:
                self.assertIsNotNone(saver)
                self.assertTrue(hasattr(saver, "get_tuple"))

    def test_thread_id_determinism(self):
        tid1 = thread_id("AAPL", "2026-05-29")
        tid2 = thread_id("AAPL", "2026-05-29")
        self.assertEqual(tid1, tid2, "same input must produce same thread_id")
        self.assertIsInstance(tid1, str)
        self.assertEqual(len(tid1), 16)

        tid3 = thread_id("AAPL", "2026-05-30")
        self.assertNotEqual(tid1, tid3, "different date must produce different thread_id")

    def test_thread_id_for_task_determinism(self):
        task = "600519:alice:scheduled"
        ttid1 = thread_id_for_task(task)
        ttid2 = thread_id_for_task(task)
        self.assertEqual(ttid1, ttid2, "same task_id must produce same thread_id")
        self.assertEqual(len(ttid1), 16)

        ttid3 = thread_id_for_task("000001:alice:scheduled")
        self.assertNotEqual(ttid1, ttid3, "different task_id must produce different thread_id")

    def test_clear_checkpoint_for_task_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clear_checkpoint_for_task(tmpdir, "no-such-task", "abc123")
            # Should not raise


if __name__ == "__main__":
    unittest.main()
