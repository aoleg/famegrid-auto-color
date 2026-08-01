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
        "Endpoint-preserving per-image auto color curves using robust shadow/highlight "
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
                        "default": 1.1,
                        "min": 0.0,
                        "max": 1.5,
                        "step": 0.05,
                        "tooltip": "Blend amount for the adaptive color and tone curves.",
                    },
                ),
                "correct_contrast": ("BOOLEAN", {"default": True}),
                "contrast_clip_percent": (
                    "FLOAT",
                    {"default": 7.3, "min": 0.0, "max": 10.0, "step": 0.1},
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
                "brightness": (
                    "FLOAT",
                    {
                        "default": 0.1,
                        "min": -1.0,
                        "max": 1.0,
                        "step": 0.05,
                        "tooltip": "Global manual brightness: negative darkens, positive brightens.",
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
    def _endpoint_preserving_map(
        values: torch.Tensor,
        dark: torch.Tensor,
        light: torch.Tensor,
        correct_contrast: bool,
    ) -> torch.Tensor:
        """Neutralize endpoint colors without flattening the histogram tails.

        Each channel uses a continuous three-segment curve through 0, the robust
        shadow anchor, the robust highlight anchor, and 1. Unlike a percentile
        stretch, values outside the anchors retain distinct tonal information.
        """
        if not correct_contrast:
            return values

        raw_span = light - dark
        if not bool(torch.all(raw_span > 0.01)):
            return values

        luminance_weights = values.new_tensor([0.299, 0.587, 0.114])
        target_dark = (dark * luminance_weights).sum().clamp(0.001, 0.45)
        target_light = (light * luminance_weights).sum().clamp(0.55, 0.999)
        if float(target_light - target_dark) < 0.05:
            return values

        dark = dark.clamp(1e-4, 0.98)
        light = torch.maximum(light, dark + 0.01).clamp_max(0.9999)
        view_shape = (1,) * (values.ndim - 1) + (3,)
        dark_view = dark.view(view_shape)
        light_view = light.view(view_shape)

        low = values * (target_dark / dark).view(view_shape)
        middle = target_dark + (values - dark_view) * (
            (target_light - target_dark) / (light - dark)
        ).view(view_shape)
        high = target_light + (values - light_view) * (
            (1.0 - target_light) / (1.0 - light)
        ).view(view_shape)
        return torch.where(
            values <= dark_view,
            low,
            torch.where(values <= light_view, middle, high),
        ).clamp(0.0, 1.0)

    @classmethod
    def _auto_color_curves(
        cls,
        rgb: torch.Tensor,
        clip_percent: float,
        correct_contrast: bool,
        strength: float,
    ) -> torch.Tensor:
        """Build full-range-preserving endpoint and neutral curves per image."""
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

            mapped = cls._endpoint_preserving_map(frame, dark, light, correct_contrast)
            mapped_sample = cls._endpoint_preserving_map(
                sample, dark, light, correct_contrast
            )

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

            # Extrapolating beyond the technical curve can create new clipping,
            # so 1.0 is the maximum effective blend even though old workflows
            # may contain a larger saved value such as the published 1.10 default.
            blend = max(0.0, min(1.0, float(strength)))
            outputs.append((frame + blend * (corrected - frame)).clamp(0.0, 1.0))

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
        return rgb.clamp(0.0, 1.0)

    def correct(
        self,
        image: torch.Tensor,
        white_balance_power: int = 8,
        auto_color_strength: float = 1.1,
        correct_contrast: bool = True,
        contrast_clip_percent: float = 7.3,
        normalize_saturation: bool = True,
        saturation_strength: float = 0.15,
        protect_skin: bool = True,
        brightness: float = 0.1,
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
            stretched = (rgb - low) / span.clamp_min(1e-7)
            rgb = torch.where(span > 1e-7, stretched, rgb).clamp(0.0, 1.0)

        if normalize_saturation and saturation_strength > 0.0:
            rgb = self._normalize_saturation(rgb, saturation_strength, protect_skin)

        rgb = self._manual_grading(
            rgb, brightness, shadows, highlights, saturation, vibrance, protect_skin
        )

        if image.shape[-1] > 3:
            output = torch.cat((rgb.to(original_dtype), image[..., 3:]), dim=-1)
        else:
            output = rgb.to(original_dtype)
        return (output,)
