"""PIL <-> ComfyUI IMAGE tensor conversion for the Forge Neo integration.

Forge's postprocessing hooks pass a single `PIL.Image` per call; node.py's
`correct()` expects a ComfyUI-shaped `[batch, height, width, channels]`
float32 tensor in `[0, 1]`. This module bridges the two without touching
node.py.
"""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image


def _normalize_mode(image: Image.Image) -> Image.Image:
    """Convert to RGB unless the image already carries an alpha channel."""
    if image.mode not in ("RGB", "RGBA"):
        return image.convert("RGB")
    return image


def image_to_tensor(image: Image.Image) -> torch.Tensor:
    """Convert an already RGB/RGBA PIL image to a `[1, H, W, C]` float32 tensor in `[0, 1]`."""
    array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def tensor_to_image(tensor: torch.Tensor, mode: str) -> Image.Image:
    """Convert a `[1, H, W, C]` float32 tensor in `[0, 1]` back to a PIL image."""
    array = tensor[0].clamp(0.0, 1.0).mul(255.0).round().to(torch.uint8).cpu().numpy()
    return Image.fromarray(array, mode=mode)


def apply(corrector, image: Image.Image, **params) -> Image.Image:
    """Run the FameGrid corrector node on a single PIL image.

    `params` keys must match node.py's `correct()` keyword arguments exactly.
    """
    normalized = _normalize_mode(image)
    tensor = image_to_tensor(normalized)
    (output,) = corrector.correct(tensor, **params)
    return tensor_to_image(output, normalized.mode)
