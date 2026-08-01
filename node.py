"""ComfyUI node for FameGrid's image-driven automatic color correction."""

from __future__ import annotations

import torch


class FameGridAutoColorCorrector:
    """Neutralize color casts and gently normalize contrast and saturation.

    ComfyUI IMAGE tensors use an RGB, channels-last layout with values in [0, 1].
    Every image in a batch is analyzed independently so one image cannot influence
    the correction applied to another.
    """

    CATEGORY = "FameGrid/Color"
    FUNCTION = "correct"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    DESCRIPTION = (
        "Deterministic per-image auto color curves using robust shadow/highlight "
        "anchors and a likely-neutral midtone, plus conservative saturation control."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "white_balance_power": (
                    "INT",
                    {
                        "default": 8,
                        "min": 0,
                        "max": 20,
                        "step": 1,
                        "tooltip": (
                            "0 disables auto color. Values above 0 enable the new curve "
                            "correction; this legacy control is retained for old workflows."
                        ),
                    },
                ),
                "auto_color_strength": (
                    "FLOAT",
                    {
                        "default": 0.8,
                        "min": 0.0,
                        "max": 1.5,
                        "step": 0.05,
                        "tooltip": (
                            "Blend amount for the adaptive color and tone curves. "
                            "Values above 1.0 extrapolate past the computed correction."
                        ),
                    },
                ),
                "correct_contrast": ("BOOLEAN", {"default": True}),
                "contrast_clip_percent": (
                    "FLOAT",
                    {
                        "default": 0.1,
                        "min": 0.0,
                        "max": 10.0,
                        "step": 0.1,
                        "tooltip": (
                            "Histogram tail used to form the shadow and highlight anchors. "
                            "Larger values crush more of the image to pure black and white; "
                            "the effective tail is floored at 0.5%."
                        ),
                    },
                ),
                "normalize_saturation": ("BOOLEAN", {"default": True}),
                "saturation_strength": (
                    "FLOAT",
                    {
                        "default": 0.15,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.05,
                        "tooltip": "Strength of automatic saturation normalization.",
                    },
                ),
                "protect_skin": ("BOOLEAN", {"default": True}),
                "preserve_hue": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Drive the endpoint curves from luminance and scale all three "
                            "channels together, so highlights roll off without rotating hue. "
                            "Disable for the pre-1.2 per-channel behavior."
                        ),
                    },
                ),
                "brightness": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": -1.0,
                        "max": 1.0,
                        "step": 0.05,
                        "tooltip": (
                            "Global manual brightness: negative darkens, positive brightens. "
                            "Weighted toward the shadow end, so positive values lift the "
                            "black point rather than shifting the whole frame evenly."
                        ),
                    },
                ),
                "shadows": (
                    "FLOAT",
                    {"default": -0.15, "min": -1.0, "max": 1.0, "step": 0.05},
                ),
                "highlights": (
                    "FLOAT",
                    {"default": -0.05, "min": -1.0, "max": 1.0, "step": 0.05},
                ),
                "saturation": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": -1.0,
                        "max": 1.0,
                        "step": 0.05,
                        "tooltip": "Manual saturation: negative reduces, positive boosts.",
                    },
                ),
                "vibrance": (
                    "FLOAT",
                    {
                        "default": -0.35,
                        "min": -1.0,
                        "max": 1.0,
                        "step": 0.05,
                        "tooltip": "Targets muted colors more than colors already saturated.",
                    },
                ),
            }
        }

    @staticmethod
    def _validate_image(image: torch.Tensor) -> None:
        if not isinstance(image, torch.Tensor):
            raise TypeError("image must be a torch.Tensor")
        if image.ndim != 4 or image.shape[-1] < 3:
            raise ValueError("image must have ComfyUI IMAGE shape [batch, height, width, channels]")

    @staticmethod
    def _percentile_per_image(values: torch.Tensor, quantile: float) -> torch.Tensor:
        """Estimate a percentile per batch item without huge quantile tensors."""
        flat = values.reshape(values.shape[0], -1)
        if flat.shape[1] > 1_000_000:
            stride = max(1, flat.shape[1] // 1_000_000)
            flat = flat[:, ::stride]
        return torch.quantile(flat, quantile, dim=1).view(-1, 1, 1, 1)

    @staticmethod
    def _rgb_saturation_and_hue(rgb: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Return HSV saturation [0, 1] and hue in degrees for an RGB tensor."""
        maximum, max_index = rgb.max(dim=-1)
        minimum = rgb.min(dim=-1).values
        delta = maximum - minimum
        saturation = torch.where(maximum > 1e-7, delta / maximum, torch.zeros_like(maximum))

        red, green, blue = rgb.unbind(dim=-1)
        safe_delta = torch.where(delta > 1e-7, delta, torch.ones_like(delta))
        red_hue = torch.remainder((green - blue) / safe_delta, 6.0)
        green_hue = (blue - red) / safe_delta + 2.0
        blue_hue = (red - green) / safe_delta + 4.0
        hue = torch.where(max_index == 0, red_hue, torch.where(max_index == 1, green_hue, blue_hue))
        hue = torch.where(delta > 1e-7, hue * 60.0, torch.zeros_like(hue))
        return saturation, hue

    @classmethod
    def _normalize_saturation(
        cls,
        rgb: torch.Tensor,
        strength: float,
        protect_skin: bool,
        low: float = 0.35,
        high: float = 0.55,
        aim_low: float = 0.40,
        aim_high: float = 0.50,
    ) -> torch.Tensor:
        saturation, hue = cls._rgb_saturation_and_hue(rgb)
        mean_saturation = saturation.mean(dim=(1, 2), keepdim=True)

        below = mean_saturation < low
        above = mean_saturation > high
        should_correct = (mean_saturation >= 1e-3) & (below | above)
        target = torch.where(below, aim_low, aim_high)
        desired = mean_saturation + strength * (target - mean_saturation)
        factor = torch.clamp(desired / mean_saturation.clamp_min(1e-7), 0.7, 1.4)
        factor = torch.where(should_correct, factor, torch.ones_like(factor))

        if protect_skin:
            # Equivalent to the source OpenCV hue mask: H < 25 or H > 170.
            skin = (hue < 50.0) | (hue > 340.0)
            pixel_factor = torch.where(skin, 1.0 + (factor - 1.0) * 0.5, factor)
        else:
            pixel_factor = factor

        new_saturation = torch.clamp(saturation * pixel_factor, 0.0, 1.0)
        maximum = rgb.max(dim=-1).values
        minimum = rgb.min(dim=-1).values
        delta = maximum - minimum
        scale = torch.where(
            saturation > 1e-7,
            new_saturation / saturation.clamp_min(1e-7),
            torch.ones_like(saturation),
        )
        normalized = maximum.unsqueeze(-1) - (maximum.unsqueeze(-1) - rgb) * scale.unsqueeze(-1)
        # Keep achromatic pixels stable and guard against accumulated numeric error.
        normalized = torch.where((delta > 1e-7).unsqueeze(-1), normalized, rgb)
        return normalized.clamp(0.0, 1.0)

    @staticmethod
    def _quantile_1d(values: torch.Tensor, quantile: float) -> torch.Tensor:
        if values.numel() > 1_000_000:
            stride = max(1, values.numel() // 1_000_000)
            values = values[::stride]
        return torch.quantile(values, quantile)

    @staticmethod
    def _soft_clip_preserve_hue(rgb: torch.Tensor, knee: float = 0.9) -> torch.Tensor:
        """Roll values above `knee` off toward 1.0 without changing hue.

        Every channel of a pixel is scaled by the same factor, so the R:G:B
        ratios are untouched. A plain per-channel ``clamp(0, 1)`` instead lets
        the brightest channel saturate first while the others keep climbing,
        which rotates highlight hue -- on skin, red saturates first and the
        result drifts yellow.

        The curve is C1-continuous at `knee` (unit slope there) and asymptotic
        to 1.0, so nothing ever lands on a flat, detail-free plateau.

        A shoulder that asymptotes to 1.0 necessarily pulls down values just
        below it too, so this is a no-op unless something actually overshoots.
        Otherwise merely enabling hue preservation would dim near-white content
        that was already perfectly in range.
        """
        rgb = rgb.clamp_min(0.0)
        peak = rgb.max(dim=-1, keepdim=True).values
        if not bool((peak > 1.0).any()):
            return rgb

        headroom = 1.0 - knee
        excess = (peak - knee).clamp_min(0.0) / headroom
        compressed = knee + headroom * (excess / (excess + 1.0))
        scale = torch.where(peak > knee, compressed / peak.clamp_min(1e-7), torch.ones_like(peak))
        return rgb * scale

    @staticmethod
    def _stretch_preserve_hue(
        rgb: torch.Tensor,
        dark: torch.Tensor,
        light: torch.Tensor,
        weights: torch.Tensor,
    ) -> torch.Tensor:
        """Apply the endpoint stretch to luminance, then scale RGB by the gain.

        The per-channel variant maps each channel against its own anchor, which
        doubles as a white balance but compresses whichever channel has least
        headroom -- rotating hue in the highlights. Here the anchors are reduced
        to luminance so the stretch is purely tonal; color correction is left to
        the neutral-midtone gamma, which is the step actually designed for it.
        """
        dark_luma = (dark * weights).sum()
        light_luma = (light * weights).sum()
        span = (light_luma - dark_luma).clamp_min(0.05)

        luma = (rgb * weights).sum(dim=-1, keepdim=True)
        target = ((luma - dark_luma) / span).clamp_min(0.0)
        return rgb * (target / luma.clamp_min(1e-6))

    @classmethod
    def _auto_color_curves(
        cls,
        rgb: torch.Tensor,
        clip_percent: float,
        correct_contrast: bool,
        strength: float,
        preserve_hue: bool = True,
    ) -> torch.Tensor:
        """Build robust endpoint and neutral-midtone curves per batch item."""
        outputs = []
        tail = max(clip_percent / 100.0, 0.005)
        luminance_weights = rgb.new_tensor([0.299, 0.587, 0.114])

        for frame in rgb:
            sample = frame.reshape(-1, 3)
            if sample.shape[0] > 1_000_000:
                stride = max(1, sample.shape[0] // 1_000_000)
                sample = sample[::stride]

            luminance = (sample * luminance_weights).sum(dim=1)
            low_luminance = cls._quantile_1d(luminance, tail)
            high_luminance = cls._quantile_1d(luminance, 1.0 - tail)
            dark = sample[luminance <= low_luminance].mean(dim=0)
            light = sample[luminance >= high_luminance].mean(dim=0)

            raw_span = light - dark
            if correct_contrast and bool(torch.all(raw_span > 0.01)):
                if preserve_hue:
                    mapped = cls._soft_clip_preserve_hue(
                        cls._stretch_preserve_hue(frame, dark, light, luminance_weights)
                    )
                    mapped_sample = cls._soft_clip_preserve_hue(
                        cls._stretch_preserve_hue(sample, dark, light, luminance_weights)
                    )
                else:
                    span = raw_span.clamp_min(0.05)
                    mapped = ((frame - dark) / span).clamp(0.0, 1.0)
                    mapped_sample = ((sample - dark) / span).clamp(0.0, 1.0)
            else:
                mapped = frame
                mapped_sample = sample

            mapped_luminance = (mapped_sample * luminance_weights).sum(dim=1)
            maximum = mapped_sample.max(dim=1).values
            minimum = mapped_sample.min(dim=1).values
            chroma = (maximum - minimum) / maximum.clamp_min(1e-7)
            midtones = (
                (mapped_luminance > 0.18)
                & (mapped_luminance < 0.82)
                & (maximum < 0.98)
            )

            if int(midtones.sum()) >= 64:
                neutral_threshold = cls._quantile_1d(chroma[midtones], 0.20)
                chroma_ceiling = cls._quantile_1d(chroma[midtones], 0.80)
                has_neutral_evidence = (
                    float(neutral_threshold) < 0.18
                    or float(chroma_ceiling - neutral_threshold) > 0.04
                )
                if has_neutral_evidence:
                    neutral = midtones & (chroma <= neutral_threshold)
                    neutral_luminance = mapped_luminance[neutral]
                    weights = 1.0 - (neutral_luminance - 0.5).abs().mul(1.5).clamp_max(0.85)
                    neutral_color = (
                        (mapped_sample[neutral] * weights[:, None]).sum(dim=0) / weights.sum()
                    )
                    target = (neutral_color * luminance_weights).sum().clamp(0.12, 0.88)
                    neutral_color = neutral_color.clamp(0.06, 0.94)
                    gamma = (target.log() / neutral_color.log()).clamp(0.55, 1.8)
                    corrected = mapped.pow(gamma)
                else:
                    corrected = mapped
            else:
                corrected = mapped

            blended = frame + strength * (corrected - frame)
            if preserve_hue:
                # strength > 1.0 extrapolates past the correction and can push
                # channels over 1.0; roll them off together rather than letting
                # the brightest one clip on its own.
                blended = cls._soft_clip_preserve_hue(blended)
            outputs.append(blended.clamp(0.0, 1.0))

        return torch.stack(outputs, dim=0)

    @staticmethod
    def _manual_grading(
        rgb: torch.Tensor,
        brightness: float,
        shadows: float,
        highlights: float,
        saturation: float,
        vibrance: float,
        protect_skin: bool,
        preserve_hue: bool = True,
    ) -> torch.Tensor:
        luminance_weights = rgb.new_tensor([0.299, 0.587, 0.114])

        def luminance(image):
            return (image * luminance_weights).sum(dim=-1)

        def adjust_tone(image, amount, mask):
            amount = max(-1.0, min(1.0, float(amount))) * 0.5
            if amount >= 0:
                return image + amount * mask[..., None] * (1.0 - image)
            return image + amount * mask[..., None] * image

        if brightness:
            rgb = adjust_tone(rgb, brightness, torch.ones_like(luminance(rgb)))

        if shadows:
            rgb = adjust_tone(rgb, shadows, (1.0 - luminance(rgb)).square())
        if highlights:
            rgb = adjust_tone(rgb, highlights, luminance(rgb).square())
        if saturation:
            gray = luminance(rgb)[..., None]
            factor = 1.0 + max(-1.0, min(1.0, float(saturation)))
            rgb = gray + (rgb - gray) * factor
        if vibrance:
            current_saturation, hue = FameGridAutoColorCorrector._rgb_saturation_and_hue(rgb)
            effect = max(-1.0, min(1.0, float(vibrance))) * (1.0 - current_saturation)
            if protect_skin:
                skin = (hue < 50.0) | (hue > 340.0)
                effect = torch.where(skin, effect * 0.5, effect)
            gray = luminance(rgb)[..., None]
            rgb = gray + (rgb - gray) * (1.0 + effect[..., None])
        if preserve_hue:
            rgb = FameGridAutoColorCorrector._soft_clip_preserve_hue(rgb)
        return rgb.clamp(0.0, 1.0)

    def correct(
        self,
        image: torch.Tensor,
        white_balance_power: int = 8,
        auto_color_strength: float = 0.8,
        correct_contrast: bool = True,
        contrast_clip_percent: float = 0.1,
        normalize_saturation: bool = True,
        saturation_strength: float = 0.15,
        protect_skin: bool = True,
        preserve_hue: bool = True,
        brightness: float = 0.0,
        shadows: float = -0.15,
        highlights: float = -0.05,
        saturation: float = 0.0,
        vibrance: float = -0.35,
    ):
        self._validate_image(image)

        original_dtype = image.dtype
        rgb = image[..., :3].to(dtype=torch.float32).clamp(0.0, 1.0)

        contrast_applied = False
        if white_balance_power > 0:
            rgb = self._auto_color_curves(
                rgb,
                contrast_clip_percent,
                correct_contrast,
                auto_color_strength,
                preserve_hue,
            )
            contrast_applied = correct_contrast

        if correct_contrast and not contrast_applied and contrast_clip_percent < 50.0:
            luminance = (
                0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
            )
            quantile = contrast_clip_percent / 100.0
            low = self._percentile_per_image(luminance, quantile)
            high = self._percentile_per_image(luminance, 1.0 - quantile)
            span = high - low
            if preserve_hue:
                # Drive the stretch from luminance and scale channels together.
                # The per-channel form subtracts a scalar from every channel,
                # which inflates saturation and lets the brightest channel clip
                # on its own -- this path has no strength blend to soften it.
                source = luminance.unsqueeze(-1)
                target = ((source - low) / span.clamp_min(1e-7)).clamp_min(0.0)
                stretched = self._soft_clip_preserve_hue(rgb * (target / source.clamp_min(1e-6)))
            else:
                stretched = (rgb - low) / span.clamp_min(1e-7)
            rgb = torch.where(span > 1e-7, stretched, rgb).clamp(0.0, 1.0)

        if normalize_saturation and saturation_strength > 0.0:
            rgb = self._normalize_saturation(rgb, saturation_strength, protect_skin)

        rgb = self._manual_grading(
            rgb, brightness, shadows, highlights, saturation, vibrance, protect_skin, preserve_hue
        )

        if image.shape[-1] > 3:
            output = torch.cat((rgb.to(original_dtype), image[..., 3:]), dim=-1)
        else:
            output = rgb.to(original_dtype)
        return (output,)
