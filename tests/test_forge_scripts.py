"""Offline stub harness for the Forge Neo txt2img/img2img script.

See tests/forge_stubs.py for the shared fake `modules`/`gradio` scaffolding
and knowledge.md #6/#9 for the methodology this implements.
"""

import sys
import unittest
from inspect import signature
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from forge_stubs import install_fake_forge_modules, install_fake_gradio, load_script_module

EXPECTED_PARAM_ORDER = [
    "enable",
    "auto_color",
    "auto_color_strength",
    "correct_contrast",
    "contrast_clip_percent",
    "normalize_saturation",
    "saturation_strength",
    "protect_skin",
    "preserve_hue",
    "brightness",
    "shadows",
    "highlights",
    "saturation",
    "vibrance",
]

# matches EXPECTED_PARAM_ORDER[1:]
DEFAULT_ARGS = (True, 0.8, True, 7.3, True, 0.15, True, True, 0.1, -0.15, -0.05, 0.0, -0.35)

_installed_module_names = []
famegrid_auto_color = None
fake_xyz_grid = None


class _FakeP:
    def __init__(self):
        self.extra_generation_params = {}


class _FakePP:
    def __init__(self, image):
        self.image = image


def setUpModule():
    global famegrid_auto_color, fake_xyz_grid

    fakes, fake_xyz_grid = install_fake_forge_modules(str(REPO_ROOT), include_xyz_grid=True)
    fakes["gradio"] = install_fake_gradio()

    for name, module in fakes.items():
        sys.modules[name] = module
        _installed_module_names.append(name)

    # lib_famegrid.xyz's registration guard is a process-global module flag;
    # force it back to "not yet registered" so this test module's fake
    # xyz_grid actually receives the axis options, regardless of what ran
    # earlier in this test process.
    import lib_famegrid.xyz as xyz_module
    xyz_module._registered = False

    famegrid_auto_color = load_script_module(REPO_ROOT / "scripts" / "famegrid_auto_color.py", "famegrid_auto_color_forge_script")


def tearDownModule():
    import lib_famegrid.xyz as xyz_module
    xyz_module._registered = False

    for name in _installed_module_names:
        sys.modules.pop(name, None)


class FameGridAutoColorScriptTests(unittest.TestCase):
    def setUp(self):
        self.script = famegrid_auto_color.FameGridAutoColorScript()
        self.script.XYZ_CACHE.clear()
        famegrid_auto_color.FameGridAutoColorScript._config = None

    def test_ui_and_hook_parameter_order_match(self):
        # drop the leading `p` and the trailing `**kwargs`
        param_names = list(signature(self.script.before_process_batch).parameters)[1:]
        param_names = [name for name in param_names if name != "kwargs"]
        self.assertEqual(param_names, EXPECTED_PARAM_ORDER)

    def test_ui_returns_one_component_per_expected_parameter(self):
        controls = self.script.ui(is_img2img=False)
        self.assertEqual(len(controls), len(EXPECTED_PARAM_ORDER))

    def test_ui_component_defaults_match_node_defaults_in_declared_order(self):
        controls = self.script.ui(is_img2img=False)
        node_defaults = famegrid_auto_color._FameGridAutoColorCorrector.INPUT_TYPES()["required"]

        self.assertEqual(controls[0].value, False)  # accordion starts collapsed/disabled

        expected = [
            node_defaults["white_balance_power"][1]["default"] > 0,
            node_defaults["auto_color_strength"][1]["default"],
            node_defaults["correct_contrast"][1]["default"],
            node_defaults["contrast_clip_percent"][1]["default"],
            node_defaults["normalize_saturation"][1]["default"],
            node_defaults["saturation_strength"][1]["default"],
            node_defaults["protect_skin"][1]["default"],
            node_defaults["preserve_hue"][1]["default"],
            node_defaults["brightness"][1]["default"],
            node_defaults["shadows"][1]["default"],
            node_defaults["highlights"][1]["default"],
            node_defaults["saturation"][1]["default"],
            node_defaults["vibrance"][1]["default"],
        ]
        for index, value in enumerate(expected, start=1):
            self.assertEqual(controls[index].value, value, f"mismatch at position {index} ({EXPECTED_PARAM_ORDER[index]})")

    def test_disabled_hook_does_not_touch_image_or_infotext(self):
        image = Image.new("RGB", (16, 16), color=(10, 20, 30))
        p = _FakeP()
        pp = _FakePP(image)

        self.script.before_process_batch(p, False, *DEFAULT_ARGS)
        self.script.postprocess_image_after_composite(p, pp)

        self.assertIs(pp.image, image)
        self.assertEqual(p.extra_generation_params, {})

    def test_enabled_hook_applies_correction_and_writes_infotext(self):
        image = Image.new("RGB", (32, 32), color=(200, 90, 40))
        original_pixels = list(image.getdata())
        p = _FakeP()
        pp = _FakePP(image)

        self.script.before_process_batch(p, True, *DEFAULT_ARGS)
        self.script.postprocess_image_after_composite(p, pp)

        self.assertNotEqual(list(pp.image.getdata()), original_pixels)
        self.assertEqual(p.extra_generation_params["FameGrid AC Auto Color"], True)
        self.assertEqual(p.extra_generation_params["FameGrid AC Brightness"], 0.1)
        self.assertEqual(len(p.extra_generation_params), len(EXPECTED_PARAM_ORDER) - 1)

    def test_auto_color_checkbox_maps_to_legacy_white_balance_power(self):
        image = Image.new("RGB", (16, 16), color=(100, 150, 200))
        p, pp = _FakeP(), _FakePP(image)

        # enable=True but every effect disabled -- image should be untouched,
        # which only holds if auto_color=False correctly maps to
        # white_balance_power=0 inside to_node_kwargs().
        self.script.before_process_batch(
            p, True, False, 0.8, False, 0.1, False, 0.15, True, True, 0.0, 0.0, 0.0, 0.0, 0.0
        )
        self.script.postprocess_image_after_composite(p, pp)

        self.assertEqual(list(pp.image.getdata()), list(image.getdata()))

    def test_all_images_in_a_batch_see_the_same_resolved_settings(self):
        # postprocess_image_after_composite fires once per image, not once
        # per batch -- before_process_batch must resolve settings exactly
        # once and every image in the batch must see that same resolution.
        p = _FakeP()
        self.script.before_process_batch(p, True, *DEFAULT_ARGS)

        images = [Image.new("RGB", (16, 16), color=(200, 90, 40)) for _ in range(3)]
        for image in images:
            self.script.postprocess_image_after_composite(p, _FakePP(image))

        pixel_sets = [list(image.getdata()) for image in images]
        self.assertEqual(pixel_sets[0], pixel_sets[1])
        self.assertEqual(pixel_sets[1], pixel_sets[2])

    def test_postprocess_resets_config_and_xyz_cache(self):
        p = _FakeP()
        self.script.XYZ_CACHE["brightness"] = 0.9
        self.script.before_process_batch(p, True, *DEFAULT_ARGS)
        self.assertIsNotNone(famegrid_auto_color.FameGridAutoColorScript._config)

        self.script.postprocess(p, processed=None)

        self.assertIsNone(famegrid_auto_color.FameGridAutoColorScript._config)
        self.assertEqual(self.script.XYZ_CACHE, {})

    def test_xyz_cache_override_takes_priority_over_ui_args(self):
        p = _FakeP()
        self.script.XYZ_CACHE["brightness"] = 0.9
        self.script.XYZ_CACHE["enable"] = "true"

        self.script.before_process_batch(p, False, *DEFAULT_ARGS)  # UI says disabled

        config = famegrid_auto_color.FameGridAutoColorScript._config
        self.assertIsNotNone(config)  # XYZ override enabled it anyway
        self.assertEqual(config["brightness"], 0.9)
        # the cache must be drained so it doesn't leak into the next batch
        self.assertEqual(self.script.XYZ_CACHE, {})

    def test_registers_axis_options_exactly_once_across_multiple_instances(self):
        before = len(fake_xyz_grid.axis_options)
        famegrid_auto_color.FameGridAutoColorScript()  # second instance, e.g. img2img ScriptRunner
        self.assertEqual(len(fake_xyz_grid.axis_options), before)


if __name__ == "__main__":
    unittest.main()
