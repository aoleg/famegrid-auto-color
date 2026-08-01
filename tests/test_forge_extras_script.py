"""Offline stub harness for the Extras-tab ScriptPostprocessing script.

See tests/forge_stubs.py for the shared fake `modules`/`gradio` scaffolding.

Unlike the txt2img/img2img script, ScriptPostprocessing.ui() returns a dict
keyed by parameter name (see modules/scripts_postprocessing.py), so there is
no positional-order alignment risk to test here -- process()'s keyword
arguments are matched by name, not position.
"""

import sys
import unittest
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from forge_stubs import install_fake_forge_modules, install_fake_gradio, load_script_module

EXPECTED_UI_KEYS = {
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
}

_installed_module_names = []
famegrid_auto_color_extras = None
_PostprocessedImage = None


def setUpModule():
    global famegrid_auto_color_extras, _PostprocessedImage

    fakes, _ = install_fake_forge_modules(str(REPO_ROOT), include_scripts_postprocessing=True)
    fakes["gradio"] = install_fake_gradio()

    for name, module in fakes.items():
        sys.modules[name] = module
        _installed_module_names.append(name)

    _PostprocessedImage = fakes["modules.scripts_postprocessing"].PostprocessedImage
    famegrid_auto_color_extras = load_script_module(REPO_ROOT / "scripts" / "famegrid_auto_color_extras.py", "famegrid_auto_color_extras_script")


def tearDownModule():
    for name in _installed_module_names:
        sys.modules.pop(name, None)


class FameGridAutoColorExtrasScriptTests(unittest.TestCase):
    def setUp(self):
        self.script = famegrid_auto_color_extras.ScriptPostprocessingFameGridAutoColor()

    def test_ui_returns_exactly_the_expected_named_controls(self):
        controls = self.script.ui()
        self.assertEqual(set(controls.keys()), EXPECTED_UI_KEYS)

    def test_ui_component_defaults_match_node_defaults(self):
        controls = self.script.ui()
        node_defaults = famegrid_auto_color_extras._FameGridAutoColorCorrector.INPUT_TYPES()["required"]

        self.assertEqual(controls["enable"].value, False)
        self.assertEqual(controls["auto_color"].value, node_defaults["white_balance_power"][1]["default"] > 0)
        self.assertEqual(controls["auto_color_strength"].value, node_defaults["auto_color_strength"][1]["default"])
        self.assertEqual(controls["brightness"].value, node_defaults["brightness"][1]["default"])
        self.assertEqual(controls["vibrance"].value, node_defaults["vibrance"][1]["default"])

    def test_disabled_process_does_not_touch_image_or_info(self):
        image = Image.new("RGB", (16, 16), color=(10, 20, 30))
        pp = _PostprocessedImage(image)

        self.script.process(pp, enable=False)

        self.assertIs(pp.image, image)
        self.assertEqual(pp.info, {})

    def test_enabled_process_applies_correction_and_writes_info(self):
        image = Image.new("RGB", (32, 32), color=(200, 90, 40))
        original_pixels = list(image.getdata())
        pp = _PostprocessedImage(image)

        self.script.process(
            pp,
            enable=True,
            auto_color=True,
            auto_color_strength=0.8,
            correct_contrast=True,
            contrast_clip_percent=0.1,
            normalize_saturation=True,
            saturation_strength=0.15,
            protect_skin=True,
            preserve_hue=True,
            brightness=0.1,
            shadows=-0.15,
            highlights=-0.05,
            saturation=0.0,
            vibrance=-0.20,
        )

        self.assertNotEqual(list(pp.image.getdata()), original_pixels)
        self.assertEqual(pp.info["FameGrid AC Auto Color"], True)
        self.assertEqual(pp.info["FameGrid AC Brightness"], 0.1)
        self.assertEqual(len(pp.info), len(EXPECTED_UI_KEYS) - 1)

    def test_process_defaults_match_node_defaults_when_only_enable_is_passed(self):
        # process()'s own kwarg defaults are a fallback if ever invoked without
        # explicit args; they should mirror node.py's published defaults.
        image = Image.new("RGB", (32, 32), color=(200, 90, 40))
        original_pixels = list(image.getdata())
        pp = _PostprocessedImage(image)

        self.script.process(pp, enable=True)

        self.assertNotEqual(list(pp.image.getdata()), original_pixels)
        self.assertEqual(pp.info["FameGrid AC Auto Color Strength"], 0.8)
        self.assertEqual(pp.info["FameGrid AC Vibrance"], -0.20)


if __name__ == "__main__":
    unittest.main()
