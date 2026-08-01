"""Unit tests for lib_famegrid/xyz.py in isolation.

test_forge_scripts.py already covers xyz.py through the real script's
before_process_batch(); this file tests xyz_support() directly: bool parsing
(the `bool("False") is True` trap), full field/label coverage, and the
once-only registration guard that matters because Forge instantiates each
Script subclass once per ScriptRunner (once for txt2img, once for img2img).
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from forge_stubs import make_fake_xyz_grid_module

_installed_module_names = []


class _ScriptClassDataStub:
    def __init__(self, script_class, module):
        self.script_class = script_class
        self.module = module


def _install_minimal_scripts_module(xyz_grid_module):
    modules_pkg = types.ModuleType("modules")
    modules_pkg.__path__ = []

    scripts_mod = types.ModuleType("modules.scripts")

    class FakeXyzGridScript:
        pass

    FakeXyzGridScript.__module__ = "xyz_grid.py"
    scripts_mod.scripts_data = [_ScriptClassDataStub(FakeXyzGridScript, xyz_grid_module)]

    modules_pkg.scripts = scripts_mod

    for name, module in {"modules": modules_pkg, "modules.scripts": scripts_mod}.items():
        sys.modules[name] = module
        _installed_module_names.append(name)


def setUpModule():
    _install_minimal_scripts_module(make_fake_xyz_grid_module())


def tearDownModule():
    for name in _installed_module_names:
        sys.modules.pop(name, None)


class XyzSupportTests(unittest.TestCase):
    def setUp(self):
        import lib_famegrid.xyz as xyz_module

        self.xyz_module = xyz_module
        self.xyz_module._registered = False

        # A fresh fake xyz_grid per test, wired into the already-installed
        # modules.scripts.scripts_data so _grid_reference() finds it.
        self.fake_xyz_grid = make_fake_xyz_grid_module()
        sys.modules["modules.scripts"].scripts_data[0].module = self.fake_xyz_grid

    def tearDown(self):
        self.xyz_module._registered = False

    def test_registers_one_axis_per_bool_and_float_field_plus_enable(self):
        cache = {}
        self.xyz_module.xyz_support(cache)

        # 6 booleans (enable + 5 from lib_famegrid.params.BOOL_FIELDS) + 10 floats
        self.assertEqual(len(self.fake_xyz_grid.axis_options), 16)

    def test_second_call_does_not_duplicate_axis_options(self):
        self.xyz_module.xyz_support({})
        first_count = len(self.fake_xyz_grid.axis_options)
        self.assertGreater(first_count, 0)

        self.xyz_module.xyz_support({})  # simulates the img2img ScriptRunner's instantiation

        self.assertEqual(len(self.fake_xyz_grid.axis_options), first_count)

    def test_bool_axis_parses_true_and_false_strings_correctly(self):
        cache = {}
        self.xyz_module.xyz_support(cache)

        brightness_axis = next(opt for opt in self.fake_xyz_grid.axis_options if opt.label == "FameGrid AC Brightness")
        enable_axis = next(opt for opt in self.fake_xyz_grid.axis_options if opt.label == "FameGrid AC Enable")

        # The float axis just writes the (already-cast) value through.
        brightness_axis.apply(None, 0.42, None)
        self.assertEqual(cache["brightness"], 0.42)

        # The critical case: bool("False") is True in Python -- xyz.py must
        # not fall into that trap for its str-typed boolean axes.
        enable_axis.apply(None, "False", None)
        self.assertEqual(cache["enable"], False)
        enable_axis.apply(None, "True", None)
        self.assertEqual(cache["enable"], True)
        enable_axis.apply(None, "true", None)  # xyz_grid cell text isn't guaranteed a fixed case
        self.assertEqual(cache["enable"], True)

    def test_every_axis_label_is_famegrid_prefixed_and_unique(self):
        cache = {}
        self.xyz_module.xyz_support(cache)

        labels = [opt.label for opt in self.fake_xyz_grid.axis_options]
        self.assertEqual(len(labels), 16)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertTrue(all(label.startswith("FameGrid AC ") for label in labels))


if __name__ == "__main__":
    unittest.main()
