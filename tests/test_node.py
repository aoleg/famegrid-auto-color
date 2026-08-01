import unittest
from pathlib import Path
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from node import FameGridAutoColorCorrector


class FameGridAutoColorCorrectorTests(unittest.TestCase):
    def setUp(self):
        self.node = FameGridAutoColorCorrector()

    def test_published_defaults(self):
        inputs = self.node.INPUT_TYPES()["required"]
        expected = {
            "white_balance_power": 8,
            "auto_color_strength": 1.1,
            "contrast_clip_percent": 7.3,
            "saturation_strength": 0.15,
            "brightness": 0.1,
            "shadows": -0.15,
            "highlights": -0.05,
            "saturation": 0.0,
            "vibrance": -0.35,
        }
        for name, value in expected.items():
            self.assertEqual(inputs[name][1]["default"], value)

    def test_output_shape_dtype_and_range(self):
        image = torch.rand(2, 48, 64, 3, dtype=torch.float32)
        output, = self.node.correct(image)
        self.assertEqual(output.shape, image.shape)
        self.assertEqual(output.dtype, image.dtype)
        self.assertTrue(torch.isfinite(output).all())
        self.assertGreaterEqual(float(output.min()), 0.0)
        self.assertLessEqual(float(output.max()), 1.0)

    def test_batch_items_are_analyzed_independently(self):
        first = torch.rand(1, 48, 64, 3)
        second = torch.zeros_like(first) + torch.tensor([0.1, 0.8, 0.2])
        first_output, = self.node.correct(first)
        batch_output, = self.node.correct(torch.cat((first, second), dim=0))
        self.assertTrue(torch.equal(first_output[0], batch_output[0]))

    def test_alpha_is_preserved(self):
        rgb = torch.rand(1, 32, 32, 3)
        alpha = torch.full((1, 32, 32, 1), 0.37)
        output, = self.node.correct(torch.cat((rgb, alpha), dim=-1))
        self.assertTrue(torch.equal(output[..., 3:], alpha))

    def test_manual_controls_are_bounded(self):
        image = torch.rand(1, 48, 64, 3)
        output, = self.node.correct(
            image,
            brightness=1.0,
            shadows=-1.0,
            highlights=1.0,
            saturation=1.0,
            vibrance=1.0,
        )
        self.assertTrue(torch.isfinite(output).all())
        self.assertGreaterEqual(float(output.min()), 0.0)
        self.assertLessEqual(float(output.max()), 1.0)

    def test_auto_curve_does_not_create_new_endpoint_clipping(self):
        ramp = torch.linspace(0.0, 1.0, 4096).reshape(1, 64, 64, 1)
        image = torch.cat(
            (
                ramp,
                torch.sqrt(ramp),
                ramp.square(),
            ),
            dim=-1,
        )
        output, = self.node.correct(
            image,
            normalize_saturation=False,
            brightness=0.0,
            shadows=0.0,
            highlights=0.0,
            saturation=0.0,
            vibrance=0.0,
        )
        self.assertLessEqual(int((output == 0.0).sum()), int((image == 0.0).sum()))
        self.assertLessEqual(int((output == 1.0).sum()), int((image == 1.0).sum()))

    def test_strength_above_one_does_not_extrapolate_technical_curve(self):
        image = torch.rand(1, 48, 64, 3)
        common = dict(
            normalize_saturation=False,
            brightness=0.0,
            shadows=0.0,
            highlights=0.0,
            saturation=0.0,
            vibrance=0.0,
        )
        at_one, = self.node.correct(image, auto_color_strength=1.0, **common)
        above_one, = self.node.correct(image, auto_color_strength=1.1, **common)
        self.assertTrue(torch.equal(at_one, above_one))


if __name__ == "__main__":
    unittest.main()
