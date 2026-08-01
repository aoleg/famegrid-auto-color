"""FameGrid Auto Color for Forge Neo -- txt2img/img2img accordion.

Runs node.py's deterministic per-image auto color correction on every
generated image via the `postprocess_image_after_composite` hook, so it
grades the final composited image (post inpaint-overlay, if any) rather than
just the inpaint crop region.

`before_process_batch` resolves the effective settings once per batch (UI
values, overridden by any active X/Y/Z Plot axis) and caches them as class
state; `postprocess_image_after_composite` -- which fires once per *image*,
not once per batch -- reads that cached state so every image in the batch
sees the same, XYZ-resolved settings.
"""

import time

import gradio as gr

from modules import scripts
from modules.infotext_utils import PasteField
from modules.ui_components import InputAccordion

from lib_famegrid.adapter import apply
from lib_famegrid.loader import load_corrector_class, node_stamp
from lib_famegrid.params import FIELDS, INFOTEXT_LABELS, INFOTEXT_PREFIX, to_infotext, to_node_kwargs
from lib_famegrid.xyz import xyz_support

_EXTENSION_ROOT = scripts.basedir()
_FameGridAutoColorCorrector = load_corrector_class(_EXTENSION_ROOT)
_corrector = _FameGridAutoColorCorrector()


class FameGridAutoColorScript(scripts.Script):
    sorting_priority = 3000

    _diagnosed = False
    _config = None
    XYZ_CACHE: dict = {}

    def __init__(self):
        xyz_support(self.XYZ_CACHE)

    def title(self):
        return "FameGrid Auto Color"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        node_defaults = _FameGridAutoColorCorrector.INPUT_TYPES()["required"]

        def default(name):
            return node_defaults[name][1]["default"]

        with InputAccordion(False, label=self.title()) as enable:
            gr.HTML(
                "Deterministic per-image auto color correction: white balance, "
                "contrast, saturation, and a manual finishing grade. "
                "Analyzed independently for every image."
            )
            with gr.Row():
                auto_color = gr.Checkbox(
                    value=default("white_balance_power") > 0,
                    label="Auto color curves",
                    info="robust shadow/highlight endpoints plus neutral-midtone correction",
                )
                auto_color_strength = gr.Slider(
                    minimum=0.0, maximum=1.5, step=0.05,
                    value=default("auto_color_strength"),
                    label="Auto Color Strength",
                )
            with gr.Row():
                correct_contrast = gr.Checkbox(
                    value=default("correct_contrast"),
                    label="Auto contrast",
                    info="part of the auto color curves; also gates the legacy percentile stretch",
                )
                contrast_clip_percent = gr.Slider(
                    minimum=0.0, maximum=10.0, step=0.1,
                    value=default("contrast_clip_percent"),
                    label="Contrast Clip Percent",
                )
            with gr.Row():
                normalize_saturation = gr.Checkbox(
                    value=default("normalize_saturation"),
                    label="Normalize saturation",
                )
                saturation_strength = gr.Slider(
                    minimum=0.0, maximum=1.0, step=0.05,
                    value=default("saturation_strength"),
                    label="Saturation Normalization Strength",
                )
            with gr.Row():
                protect_skin = gr.Checkbox(
                    value=default("protect_skin"),
                    label="Protect skin hues",
                    info="reduces automatic saturation and manual vibrance changes on skin hues",
                )
                preserve_hue = gr.Checkbox(
                    value=default("preserve_hue"),
                    label="Preserve hue in highlights",
                    info="rolls highlights off without letting the brightest channel clip alone",
                )
            with gr.Row():
                shadow_depth = gr.Slider(
                    minimum=0.0, maximum=1.0, step=0.05,
                    value=default("shadow_depth"),
                    label="Shadow depth",
                    info="higher deepens blacks and buys midtone contrast; lower keeps shadow separation",
                )
                highlight_rolloff = gr.Slider(
                    minimum=0.0, maximum=1.0, step=0.05,
                    value=default("highlight_rolloff"),
                    label="Highlight rolloff",
                    info="higher softens highlights, but flattens lit skin before it buys contrast",
                )
            with gr.Row():
                brightness = gr.Slider(minimum=-1.0, maximum=1.0, step=0.05, value=default("brightness"), label="Brightness")
                shadows = gr.Slider(minimum=-1.0, maximum=1.0, step=0.05, value=default("shadows"), label="Shadows")
            with gr.Row():
                highlights = gr.Slider(minimum=-1.0, maximum=1.0, step=0.05, value=default("highlights"), label="Highlights")
                saturation = gr.Slider(minimum=-1.0, maximum=1.0, step=0.05, value=default("saturation"), label="Saturation")
            vibrance = gr.Slider(minimum=-1.0, maximum=1.0, step=0.05, value=default("vibrance"), label="Vibrance")

        # Order must match FIELDS exactly -- before_process_batch() zips
        # positional args from this same UI list against FIELDS by position.
        controls = [
            auto_color, auto_color_strength, correct_contrast, contrast_clip_percent,
            normalize_saturation, saturation_strength, protect_skin, preserve_hue,
            shadow_depth, highlight_rolloff,
            brightness, shadows, highlights, saturation, vibrance,
        ]
        self.infotext_fields = [
            PasteField(component, f"{INFOTEXT_PREFIX} {INFOTEXT_LABELS[field]}")
            for component, field in zip(controls, FIELDS)
        ]

        return [enable, *controls]

    def before_process_batch(
        self,
        p,
        enable,
        auto_color,
        auto_color_strength,
        correct_contrast,
        contrast_clip_percent,
        normalize_saturation,
        saturation_strength,
        protect_skin,
        preserve_hue,
        shadow_depth,
        highlight_rolloff,
        brightness,
        shadows,
        highlights,
        saturation,
        vibrance,
        **kwargs,
    ):
        cache = self.XYZ_CACHE
        raw = {
            "auto_color": auto_color,
            "auto_color_strength": auto_color_strength,
            "correct_contrast": correct_contrast,
            "contrast_clip_percent": contrast_clip_percent,
            "normalize_saturation": normalize_saturation,
            "saturation_strength": saturation_strength,
            "protect_skin": protect_skin,
            "preserve_hue": preserve_hue,
            "shadow_depth": shadow_depth,
            "highlight_rolloff": highlight_rolloff,
            "brightness": brightness,
            "shadows": shadows,
            "highlights": highlights,
            "saturation": saturation,
            "vibrance": vibrance,
        }
        enable = bool(cache.get("enable", enable))
        resolved = {field: cache.get(field, raw[field]) for field in FIELDS}
        cache.clear()

        FameGridAutoColorScript._config = resolved if enable else None

    def postprocess_image_after_composite(self, p, pp, *args):
        config = FameGridAutoColorScript._config
        if config is None:
            return

        node_kwargs = to_node_kwargs(config)

        if not FameGridAutoColorScript._diagnosed:
            FameGridAutoColorScript._diagnosed = True
            # node.py's mtime identifies which build is actually live -- the
            # cheapest way to tell "the pull didn't land" from "the pull landed
            # and the output is genuinely unchanged".
            _, mtime_ns, size = node_stamp(_EXTENSION_ROOT)
            stamp = "missing" if mtime_ns is None else f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime_ns / 1e9))} ({size}B)"
            print(f"[FameGridAutoColor] diagnostic: node.py={stamp} image mode={pp.image.mode} size={pp.image.size} params={node_kwargs}")

        pp.image = apply(_corrector, pp.image, **node_kwargs)
        p.extra_generation_params.update(to_infotext(config))

    def postprocess(self, p, processed, *args):
        FameGridAutoColorScript._config = None
        self.XYZ_CACHE.clear()
