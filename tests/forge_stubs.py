"""Shared fake Forge Neo `modules`/`gradio` pieces for the offline stub-harness tests.

Not a test file itself -- imported by test_forge_scripts.py,
test_forge_extras_script.py, and test_xyz.py so the fake `Script`,
`ScriptPostprocessing`, `InputAccordion`, `gradio`, and `xyz_grid` scaffolding
isn't hand-duplicated in each. See knowledge.md #6/#9 for the methodology:
exercise the real script files (loaded via spec_from_file_location, same as
Forge's own modules.script_loading.load_module()) against these fakes,
instead of predicting behavior from reading Forge source alone.
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path


class Component:
    def __init__(self, *args, **kwargs):
        self.value = kwargs.get("value")
        self.label = kwargs.get("label")
        self.info = kwargs.get("info")


class Container(Component):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def install_fake_gradio() -> types.ModuleType:
    gr_mod = types.ModuleType("gradio")
    gr_mod.HTML = Component
    gr_mod.Checkbox = Component
    gr_mod.Slider = Component
    gr_mod.Row = Container
    gr_mod.Column = Container
    gr_mod.Group = Container
    gr_mod.Accordion = Container
    return gr_mod


class FakeAxisOption:
    def __init__(self, label, type, apply, format_value=None, confirm=None, cost=0.0, choices=None, prepare=None):
        self.label = label
        self.type = type
        self.apply = apply
        self.choices = choices


def _boolean_choice(reverse: bool = False):
    def choice():
        return ["False", "True"] if reverse else ["True", "False"]

    return choice


class _ScriptClassDataStub:
    def __init__(self, script_class, module):
        self.script_class = script_class
        self.module = module


def make_fake_xyz_grid_module() -> types.ModuleType:
    """A fake xyz_grid.py exposing just what lib_famegrid/xyz.py touches."""
    xyz_grid_mod = types.ModuleType("xyz_grid")
    xyz_grid_mod.AxisOption = FakeAxisOption
    xyz_grid_mod.boolean_choice = _boolean_choice
    xyz_grid_mod.axis_options = []
    return xyz_grid_mod


def install_fake_forge_modules(
    extension_root: str,
    *,
    include_scripts_postprocessing: bool = False,
    include_xyz_grid: bool = False,
):
    """Build a dict of {module_name: fake module} ready for sys.modules.

    Returns `(modules, xyz_grid_module_or_None)` -- the caller gets the fake
    xyz_grid module directly so it can inspect `axis_options` after the real
    script under test registers its axes. If
    `include_scripts_postprocessing`, `modules["modules.scripts_postprocessing"]`
    carries `.PostprocessedImage` for constructing test fixtures.
    """
    modules_pkg = types.ModuleType("modules")
    modules_pkg.__path__ = []

    scripts_mod = types.ModuleType("modules.scripts")
    scripts_mod.basedir = lambda: extension_root

    class AlwaysVisibleType:
        pass

    class Script:
        sorting_priority = 0

        def show(self, is_img2img):
            return None

        def ui(self, is_img2img):
            return []

        def before_process_batch(self, p, *args, **kwargs):
            pass

        def postprocess_image_after_composite(self, p, pp, *args):
            pass

        def postprocess(self, p, processed, *args):
            pass

    scripts_mod.Script = Script
    scripts_mod.AlwaysVisible = AlwaysVisibleType()

    fake_xyz_grid = None
    if include_xyz_grid:
        fake_xyz_grid = make_fake_xyz_grid_module()

        class FakeXyzGridScript:
            pass

        FakeXyzGridScript.__module__ = "xyz_grid.py"
        scripts_mod.scripts_data = [_ScriptClassDataStub(FakeXyzGridScript, fake_xyz_grid)]
    else:
        scripts_mod.scripts_data = []

    ui_components_mod = types.ModuleType("modules.ui_components")

    class InputAccordion:
        def __init__(self, value=False, label=None, **kwargs):
            self.value = value
            self.label = label

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    ui_components_mod.InputAccordion = InputAccordion

    infotext_utils_mod = types.ModuleType("modules.infotext_utils")

    class PasteField:
        def __init__(self, component, api=None, **kwargs):
            self.component = component
            self.api = api

    infotext_utils_mod.PasteField = PasteField

    modules_pkg.scripts = scripts_mod
    modules_pkg.ui_components = ui_components_mod
    modules_pkg.infotext_utils = infotext_utils_mod

    modules = {
        "modules": modules_pkg,
        "modules.scripts": scripts_mod,
        "modules.ui_components": ui_components_mod,
        "modules.infotext_utils": infotext_utils_mod,
    }

    if include_scripts_postprocessing:
        scripts_postprocessing_mod = types.ModuleType("modules.scripts_postprocessing")

        class PostprocessedImage:
            def __init__(self, image):
                self.image = image
                self.info = {}

        class ScriptPostprocessing:
            order = 1000
            name = None
            group = None

            def ui(self):
                return {}

            def process(self, pp, **args):
                pass

            def process_firstpass(self, pp, **args):
                pass

            def image_changed(self):
                pass

        scripts_postprocessing_mod.PostprocessedImage = PostprocessedImage
        scripts_postprocessing_mod.ScriptPostprocessing = ScriptPostprocessing

        modules_pkg.scripts_postprocessing = scripts_postprocessing_mod
        modules["modules.scripts_postprocessing"] = scripts_postprocessing_mod

    return modules, fake_xyz_grid


def load_script_module(path: Path, module_name: str):
    """Load a script file exactly the way Forge's script_loading.load_module() does."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
