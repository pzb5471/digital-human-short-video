import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.locking import exclusive_process_lock


def _acquire_lock(lock_path, acquired_path):
    with exclusive_process_lock(lock_path):
        Path(acquired_path).write_text("acquired", encoding="utf-8")


class ProcessLockTests(unittest.TestCase):
    def test_exception_releases_lock_for_an_independent_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock_path = root / "compose.lock"
            with self.assertRaises(RuntimeError):
                with exclusive_process_lock(lock_path):
                    raise RuntimeError("injected composer failure")

            acquired = root / "acquired"
            process = multiprocessing.get_context("spawn").Process(
                target=_acquire_lock, args=(lock_path, acquired)
            )
            process.start()
            process.join(timeout=10)
            try:
                self.assertEqual(0, process.exitcode)
                self.assertTrue(acquired.is_file())
            finally:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
