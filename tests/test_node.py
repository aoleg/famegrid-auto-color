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
            "contrast_clip_percent": 7.3,
            "saturation_strength": 0.15,
            "brightness": 0.1,
            "shadows": -0.15,
            "highlights": -0.05,
            "saturation": 0.0,
            "vibrance": -0.20,
            "shadow_depth": 0.5,
            "highlight_rolloff": 0.0,
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

        # The clamped percentile stretch that originally rotated this highlight
        # ~26 degrees toward yellow is gone: preserve_hue drives the curve from
        # luminance, and the per-channel path is now the endpoint-preserving
        # curve, which never clamps. Both must stay stable, with the
        # luminance-driven path exact by construction.
        self.assertLess(drift_preserved, 0.5)
        self.assertLess(drift_legacy, 2.0)

    def test_preserve_hue_avoids_the_flat_white_plateau(self):
        image = torch.rand(1, 64, 64, 3) * 0.5 + 0.45
        preserved, = self.node.correct(image.clone(), preserve_hue=True)
        legacy, = self.node.correct(image.clone(), preserve_hue=False)

        def all_channels_maxed(t):
            return float((t >= t.max() - 1e-6).all(dim=-1).float().mean())

        self.assertLessEqual(all_channels_maxed(preserved), all_channels_maxed(legacy))

    def test_highlight_tail_compression_is_bounded_at_any_clip(self):
        """Content above the highlight anchor must keep its tonal separation.

        A fixed highlight target gives that whole tail a fixed slice of the
        output range, so a large contrast_clip_percent -- which pushes the
        anchor down into real subject matter -- squeezed it by ~11x. Bright
        skin and pale fabric then lost their separation and read as blown
        without a single pixel actually clipping.
        """
        weights = torch.tensor([0.299, 0.587, 0.114])
        for clip in (0.1, 3.0, 7.3, 10.0):
            image = torch.zeros(1, 128, 128, 3)
            image[:] = torch.linspace(0.05, 0.95, 128).view(1, 128, 1, 1)

            flat = image.reshape(-1, 3)
            luma = (flat * weights).sum(dim=-1)
            tail = max(clip / 100.0, 0.005)
            light = flat[luma >= torch.quantile(luma, 1.0 - tail)].mean(dim=0)
            dark = flat[luma <= torch.quantile(luma, tail)].mean(dim=0)

            mapped = self.node._stretch_preserve_hue(image, dark, light, weights)
            light_luma = float((light * weights).sum())

            # Measure the realised slope of the segment above the anchor.
            probe = torch.tensor([[[[light_luma, light_luma, light_luma]]]])
            top = torch.tensor([[[[1.0, 1.0, 1.0]]]])
            at_anchor = float(self.node._stretch_preserve_hue(probe, dark, light, weights).max())
            at_top = float(self.node._stretch_preserve_hue(top, dark, light, weights).max())
            slope = (at_top - at_anchor) / max(1.0 - light_luma, 1e-6)

            self.assertGreater(slope, 0.5, f"highlight tail over-compressed at clip={clip}")
            self.assertTrue(torch.isfinite(mapped).all())

    def test_shadow_tail_compression_is_bounded_at_any_clip(self):
        """Content below the shadow anchor must keep its tonal separation.

        A fixed absolute shadow target couples the compression to wherever the
        anchor lands: at the default contrast_clip_percent, a target of 0.005
        against an anchor at 0.061 crushed the tail 12x and cost the darkest
        decile a third of its distinct levels.
        """
        weights = torch.tensor([0.299, 0.587, 0.114])
        for clip in (0.1, 3.0, 7.3, 10.0):
            image = torch.zeros(1, 128, 128, 3)
            image[:] = torch.linspace(0.05, 0.95, 128).view(1, 128, 1, 1)

            flat = image.reshape(-1, 3)
            luma = (flat * weights).sum(dim=-1)
            tail = max(clip / 100.0, 0.005)
            dark = flat[luma <= torch.quantile(luma, tail)].mean(dim=0)
            light = flat[luma >= torch.quantile(luma, 1.0 - tail)].mean(dim=0)
            dark_luma = float((dark * weights).sum())

            probe = torch.tensor([[[[dark_luma, dark_luma, dark_luma]]]])
            at_anchor = float(self.node._stretch_preserve_hue(probe, dark, light, weights).max())
            slope = at_anchor / max(dark_luma, 1e-6)

            self.assertGreater(slope, 0.25, f"shadow tail over-compressed at clip={clip}")

    def test_positive_brightness_does_not_desaturate(self):
        """A brightness lift must not flatten colour.

        Adding the same offset to every channel raises `max` while leaving
        `max - min`, so saturation drops -- worst in the darker, saturated
        regions that carry facial modelling. On a test portrait that cost the
        face 12% of its saturation and read as a flattened nose.
        """
        rgb = torch.tensor([[[[0.60, 0.45, 0.40], [0.30, 0.18, 0.14]]]])

        def mean_saturation(t):
            saturation, _ = self.node._rgb_saturation_and_hue(t)
            return float(saturation.mean())

        before = mean_saturation(rgb)
        preserved = self.node._manual_grading(rgb, 0.2, 0.0, 0.0, 0.0, 0.0, False, True)
        legacy = self.node._manual_grading(rgb, 0.2, 0.0, 0.0, 0.0, 0.0, False, False)

        self.assertGreater(float(preserved.mean()), float(rgb.mean()))  # it did brighten
        self.assertAlmostEqual(mean_saturation(preserved), before, places=4)
        self.assertLess(mean_saturation(legacy), before - 0.01)

    def test_brightness_does_not_amplify_deep_shadow_noise(self):
        """The saturation-preserving gain explodes near black; it must not be used there.

        What matters is the channel spread, not the absolute lift: brightness
        is *supposed* to raise a near-black pixel. An unbounded multiplicative
        gain would blow this pixel's 0.001 spread up ~78x, turning shadow
        quantisation noise into visible colour mottling.
        """
        near_black = torch.tensor([[[[0.002, 0.001, 0.001]]]])
        spread_before = float(near_black.max() - near_black.min())

        out = self.node._manual_grading(near_black, 0.2, 0.0, 0.0, 0.0, 0.0, False, True)
        spread_after = float(out.max() - out.min())

        self.assertLess(spread_after / spread_before, 5.0)
        self.assertTrue(torch.isfinite(out).all())

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
        # The cap guards the per-channel curve, which has no shoulder and would
        # clip if extrapolated past. With preserve_hue on, the hue-preserving
        # shoulder absorbs the overshoot, so strength above 1.0 stays meaningful
        # there and is deliberately not capped.
        image = torch.rand(1, 48, 64, 3)
        common = dict(
            normalize_saturation=False,
            brightness=0.0,
            shadows=0.0,
            highlights=0.0,
            saturation=0.0,
            vibrance=0.0,
        )
        at_one, = self.node.correct(image, auto_color_strength=1.0, preserve_hue=False, **common)
        above_one, = self.node.correct(image, auto_color_strength=1.1, preserve_hue=False, **common)
        self.assertTrue(torch.equal(at_one, above_one))

    def test_strength_above_one_still_applies_when_preserving_hue(self):
        image = torch.rand(1, 48, 64, 3)
        common = dict(
            normalize_saturation=False,
            brightness=0.0,
            shadows=0.0,
            highlights=0.0,
            saturation=0.0,
            vibrance=0.0,
            preserve_hue=True,
        )
        at_one, = self.node.correct(image, auto_color_strength=1.0, **common)
        above_one, = self.node.correct(image, auto_color_strength=1.3, **common)
        self.assertFalse(torch.equal(at_one, above_one))


if __name__ == "__main__":
    unittest.main()
