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


if __name__ == "__main__":
    unittest.main()
