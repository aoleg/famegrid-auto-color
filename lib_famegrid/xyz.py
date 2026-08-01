"""X/Y/Z Plot axis support for FameGrid Auto Color's Forge Neo controls.

xyz_grid.py's own `AxisOption.apply` functions write directly onto `p`
(`setattr(p, field, x)`), but FameGrid's controls aren't `p` attributes --
they're plain arguments threaded through `before_process_batch()` /
`postprocess_image_after_composite()`. So each axis instead writes into a
shared `cache` dict that the calling script reads from (and clears) in its
own `before_process_batch()`, mirroring sd-forge-sve's lib_sve/xyz_sve.py.

Boolean fields use `type=str` with a "True"/"False" choices list and manual
parsing inside `apply`, not `type=bool` -- matching xyz_grid.py's own
convention for e.g. "Always discard next-to-last sigma". `bool("False")` is
`True` in Python, so a raw `type=bool` axis would silently ignore "False".
"""

from __future__ import annotations

from lib_famegrid.params import BOOL_FIELDS, FLOAT_FIELDS, INFOTEXT_LABELS, INFOTEXT_PREFIX

_registered = False

# "enable" (the accordion's own on/off switch) isn't one of the 12 grading
# fields in lib_famegrid.params, but it needs an axis too.
_BOOL_FIELDS = ("enable", *BOOL_FIELDS)
_FLOAT_FIELDS = FLOAT_FIELDS

_LABELS = {"enable": f"{INFOTEXT_PREFIX} Enable"}
_LABELS.update({field: f"{INFOTEXT_PREFIX} {label}" for field, label in INFOTEXT_LABELS.items()})


def _grid_reference():
    from modules import scripts  # resolved at call time, not at this module's own import time

    for data in scripts.scripts_data:
        if data.script_class.__module__ in ("scripts.xyz_grid", "xyz_grid.py") and hasattr(data, "module"):
            return data.module

    raise SystemError("Could not find X/Y/Z Plot...")


def _parse_bool(x) -> bool:
    return str(x).strip().lower() == "true"


def xyz_support(cache: dict):
    """Register FameGrid Auto Color's controls as X/Y/Z Plot axes.

    Safe to call more than once: Forge instantiates each Script subclass once
    per ScriptRunner (once for the txt2img tab, once for img2img) at
    UI-build time, regardless of `show()`'s result -- without this guard the
    axis list would gain a duplicate set of "FameGrid AC ..." entries.
    """
    global _registered
    if _registered:
        return

    xyz_grid = _grid_reference()
    boolean_choices = xyz_grid.boolean_choice(reverse=True)

    def apply_bool_field(field):
        def _(p, x, xs):
            cache[field] = _parse_bool(x)

        return _

    def apply_float_field(field):
        def _(p, x, xs):
            cache[field] = float(x)

        return _

    extra_axis_options = [
        xyz_grid.AxisOption(_LABELS[field], str, apply_bool_field(field), choices=boolean_choices)
        for field in _BOOL_FIELDS
    ] + [
        xyz_grid.AxisOption(_LABELS[field], float, apply_float_field(field))
        for field in _FLOAT_FIELDS
    ]

    xyz_grid.axis_options.extend(extra_axis_options)
    _registered = True
