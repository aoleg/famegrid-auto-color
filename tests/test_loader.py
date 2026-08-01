"""Tests for lib_famegrid/loader.py's reload behaviour.

Forge's "Reload UI" re-executes scripts/*.py but leaves lib_famegrid in
sys.modules. A permanently-cached node.py therefore kept serving whatever was
on disk at process start, so a `git pull` appeared to change nothing until the
whole process was restarted -- observed in the field as two byte-identical
generations across an update.
"""

import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import lib_famegrid.loader as loader

NODE_SRC = """
class FameGridAutoColorCorrector:
    MARKER = {marker!r}
"""


class LoaderReloadTests(unittest.TestCase):
    def setUp(self):
        self._saved = (loader._cached_module, loader._cached_stamp)
        loader._cached_module = None
        loader._cached_stamp = None

    def tearDown(self):
        loader._cached_module, loader._cached_stamp = self._saved
        sys.modules.pop(loader._MODULE_NAME, None)

    def _write(self, root, marker):
        (Path(root) / "node.py").write_text(NODE_SRC.format(marker=marker), encoding="utf-8")

    def test_reimports_when_node_py_changes_on_disk(self):
        with TemporaryDirectory() as root:
            self._write(root, "before")
            self.assertEqual(loader.load_corrector_class(root).MARKER, "before")

            # Same process, no re-import of lib_famegrid -- exactly the state a
            # soft UI reload leaves behind after a pull.
            time.sleep(0.01)
            self._write(root, "after")
            self.assertEqual(loader.load_corrector_class(root).MARKER, "after")

    def test_reuses_the_cached_module_when_nothing_changed(self):
        with TemporaryDirectory() as root:
            self._write(root, "stable")
            first = loader.load_node_module(root)
            second = loader.load_node_module(root)
            self.assertIs(first, second)

    def test_missing_node_py_reports_a_null_stamp(self):
        with TemporaryDirectory() as root:
            path, mtime_ns, size = loader.node_stamp(root)
            self.assertTrue(path.endswith("node.py"))
            self.assertIsNone(mtime_ns)
            self.assertIsNone(size)


if __name__ == "__main__":
    unittest.main()
