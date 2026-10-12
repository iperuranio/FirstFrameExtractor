"""--quit for real: a listener in this process, a --quit copy in another, over a local socket of the test's own name."""

import os
import subprocess
import sys
import time
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication  # noqa: E402

import single_instance  # noqa: E402
from single_instance import EXIT_BUSY, EXIT_CLOSING, EXIT_NONE_OPEN, QuitListener  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = QCoreApplication.instance() or QCoreApplication([])


def quit_copy(name):
    """A copy started with --quit, as Nexus starts it: its exit code, while this process keeps answering."""
    child = subprocess.Popen(
        [sys.executable, "-c", f"import sys, single_instance; sys.exit(single_instance.request_quit({name!r}))"],
        cwd=ROOT,
    )
    deadline = time.monotonic() + 15
    while child.poll() is None:
        APP.processEvents()
        time.sleep(0.01)
        if time.monotonic() > deadline:
            child.kill()
            raise AssertionError("the --quit copy did not end")
    return child.returncode


class QuitTest(unittest.TestCase):
    def setUp(self):
        self.name = f"ffe-test-{uuid.uuid4().hex[:12]}"
        self.closed = 0

    def listener(self, busy=False):
        def close():
            self.closed += 1

        listener = QuitListener(busy=lambda: busy, close=close, name=self.name)
        # Held by the test, as main() holds it: a listener collected stops answering.
        self.held = listener
        self.addCleanup(listener.server.close)
        self.assertTrue(listener.listening)
        return listener

    def test_closes_the_open_copy(self):
        self.listener()
        self.assertEqual(quit_copy(self.name), EXIT_CLOSING)
        self.assertEqual(self.closed, 1)

    def test_an_extraction_running_keeps_it_open(self):
        self.listener(busy=True)
        self.assertEqual(quit_copy(self.name), EXIT_BUSY)
        self.assertEqual(self.closed, 0)

    def test_says_when_no_copy_is_open(self):
        self.assertEqual(quit_copy(self.name), EXIT_NONE_OPEN)

    def test_a_second_open_copy_leaves_the_answer_to_the_first(self):
        first = self.listener()
        self.assertTrue(first.listening)
        second = QuitListener(busy=lambda: False, close=lambda: None, name=self.name)
        self.addCleanup(second.server.close)
        self.assertFalse(second.listening)


if __name__ == "__main__":
    unittest.main()
