import unittest
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from node import FameGridAutoColorCorrector
from lib_famegrid.adapter import apply, image_to_tensor, tensor_to_image


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.corrector = FameGridAutoColorCorrector()

    def test_rgb_round_trip_shape_and_mode(self):
        image = Image.new("RGB", (64, 48), color=(120, 60, 200))
        tensor = image_to_tensor(image)
        self.assertEqual(tuple(tensor.shape), (1, 48, 64, 3))
        self.assertAlmostEqual(float(tensor[0, 0, 0, 0]), 120 / 255.0, places=6)

        restored = tensor_to_image(tensor, "RGB")
        self.assertEqual(restored.mode, "RGB")
        self.assertEqual(restored.size, (64, 48))

    def test_rgba_alpha_is_preserved_through_apply(self):
        image = Image.new("RGBA", (32, 32), color=(10, 200, 30, 77))
        output = apply(self.corrector, image, white_balance_power=0, correct_contrast=False, normalize_saturation=False)
        self.assertEqual(output.mode, "RGBA")
        self.assertEqual(output.size, (32, 32))
        alpha_values = set(output.getchannel("A").getdata())
        self.assertEqual(alpha_values, {77})

    def test_non_rgb_mode_is_converted_before_processing(self):
        image = Image.new("L", (16, 16), color=128)
        output = apply(self.corrector, image, white_balance_power=0, correct_contrast=False, normalize_saturation=False)
        self.assertEqual(output.mode, "RGB")
        self.assertEqual(output.size, (16, 16))

    def test_apply_is_a_no_op_with_all_effects_disabled(self):
        image = Image.new("RGB", (20, 20), color=(50, 150, 250))
        output = apply(
            self.corrector,
            image,
            white_balance_power=0,
            correct_contrast=False,
            normalize_saturation=False,
            brightness=0.0,
            shadows=0.0,
            highlights=0.0,
            saturation=0.0,
            vibrance=0.0,
        )
        self.assertEqual(list(output.getdata()), list(image.getdata()))

    def test_apply_with_published_defaults_changes_the_image(self):
        image = Image.new("RGB", (48, 48), color=(200, 90, 40))
        output = apply(self.corrector, image)
        self.assertNotEqual(list(output.getdata()), list(image.getdata()))


if __name__ == "__main__":
    unittest.main()
