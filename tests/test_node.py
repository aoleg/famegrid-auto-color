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
            "auto_color_strength": 0.8,
            "contrast_clip_percent": 0.1,
            "saturation_strength": 0.15,
            "brightness": 0.0,
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

    def test_soft_clip_preserves_channel_ratios(self):
        # A pixel pushed past 1.0 must come back with its R:G:B ratios intact.
        rgb = torch.tensor([[[[1.4, 1.05, 0.90]]]])
        out = self.node._soft_clip_preserve_hue(rgb)
        self.assertLess(float(out.max()), 1.0)
        for channel in range(3):
            self.assertAlmostEqual(
                float(out[..., channel] / out[..., 0]),
                float(rgb[..., channel] / rgb[..., 0]),
                places=5,
            )

    def test_soft_clip_is_identity_below_the_knee(self):
        rgb = torch.tensor([[[[0.80, 0.55, 0.30]]]])
        out = self.node._soft_clip_preserve_hue(rgb, knee=0.9)
        self.assertTrue(torch.allclose(out, rgb))

    def _scene_with_skin_highlight(self):
        """A gray ramp plus a small warm patch brighter than the highlight anchor.

        This is the condition that produced the reported artifact: sunlit skin
        sitting above the light anchor, so the endpoint stretch pushes red past
        1.0 while green and blue still have headroom.
        """
        image = torch.zeros(1, 128, 128, 3)
        image[:] = torch.linspace(0.10, 0.78, 128).view(1, 128, 1, 1)
        image[0, :4, :4] = torch.tensor([0.90, 0.78, 0.74])
        return image

    def _hue_of_skin(self, image):
        _, hue = self.node._rgb_saturation_and_hue(image[:, :1, :1, :])
        return float(hue.reshape(-1)[0])

    def test_preserve_hue_keeps_bright_skin_hue_stable(self):
        image = self._scene_with_skin_highlight()
        before = self._hue_of_skin(image)

        preserved, = self.node.correct(image.clone(), preserve_hue=True)
        legacy, = self.node.correct(image.clone(), preserve_hue=False)

        drift_preserved = abs(self._hue_of_skin(preserved) - before)
        drift_legacy = abs(self._hue_of_skin(legacy) - before)

        # The legacy per-channel path rotates this highlight ~26 degrees toward
        # yellow; the preserved path must hold it essentially exactly.
        self.assertGreater(drift_legacy, 10.0)
        self.assertLess(drift_preserved, 0.5)

    def test_preserve_hue_avoids_the_flat_white_plateau(self):
        image = torch.rand(1, 64, 64, 3) * 0.5 + 0.45
        preserved, = self.node.correct(image.clone(), preserve_hue=True)
        legacy, = self.node.correct(image.clone(), preserve_hue=False)

        def all_channels_maxed(t):
            return float((t >= t.max() - 1e-6).all(dim=-1).float().mean())

        self.assertLessEqual(all_channels_maxed(preserved), all_channels_maxed(legacy))

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
