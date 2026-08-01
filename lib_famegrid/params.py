"""Shared parameter metadata for the Forge Neo scripts and X/Y/Z Plot axes.

Single source of truth for FameGrid Auto Color's 12 grading controls (the
accordion/operation's own enable flag is handled separately by each caller),
so the field list, infotext labels, and node.py keyword-argument mapping
can't drift apart across scripts/famegrid_auto_color.py,
scripts/famegrid_auto_color_extras.py, and lib_famegrid/xyz.py.
"""

from __future__ import annotations

BOOL_FIELDS = (
    "auto_color", "correct_contrast", "normalize_saturation", "protect_skin", "preserve_hue",
)
FLOAT_FIELDS = (
    "auto_color_strength",
    "contrast_clip_percent",
    "saturation_strength",
    "brightness",
    "shadows",
    "highlights",
    "saturation",
    "vibrance",
)
FIELDS = (
    "auto_color", "auto_color_strength", "correct_contrast", "contrast_clip_percent",
    "normalize_saturation", "saturation_strength", "protect_skin", "preserve_hue",
    "brightness", "shadows", "highlights", "saturation", "vibrance",
)

INFOTEXT_PREFIX = "FameGrid AC"
INFOTEXT_LABELS = {
    "auto_color": "Auto Color",
    "auto_color_strength": "Auto Color Strength",
    "correct_contrast": "Contrast",
    "contrast_clip_percent": "Contrast Clip",
    "normalize_saturation": "Saturation Norm",
    "saturation_strength": "Saturation Norm Strength",
    "protect_skin": "Protect Skin",
    "preserve_hue": "Preserve Hue",
    "brightness": "Brightness",
    "shadows": "Shadows",
    "highlights": "Highlights",
    "saturation": "Saturation",
    "vibrance": "Vibrance",
}


def to_node_kwargs(values: dict) -> dict:
    """Map this repo's field names to node.py's `correct()` keyword arguments.

    `values["auto_color"]` (a bool) becomes node.py's legacy
    `white_balance_power` gate (`8` enables the curve correction, `0`
    disables it -- any value above 0 behaves identically, see node.py).
    """
    return dict(
        white_balance_power=8 if bool(values["auto_color"]) else 0,
        auto_color_strength=float(values["auto_color_strength"]),
        correct_contrast=bool(values["correct_contrast"]),
        contrast_clip_percent=float(values["contrast_clip_percent"]),
        normalize_saturation=bool(values["normalize_saturation"]),
        saturation_strength=float(values["saturation_strength"]),
        protect_skin=bool(values["protect_skin"]),
        preserve_hue=bool(values["preserve_hue"]),
        brightness=float(values["brightness"]),
        shadows=float(values["shadows"]),
        highlights=float(values["highlights"]),
        saturation=float(values["saturation"]),
        vibrance=float(values["vibrance"]),
    )


def to_infotext(values: dict) -> dict:
    """Map this repo's field names to `"{INFOTEXT_PREFIX} <Label>"` keys."""
    return {f"{INFOTEXT_PREFIX} {INFOTEXT_LABELS[field]}": values[field] for field in FIELDS}
