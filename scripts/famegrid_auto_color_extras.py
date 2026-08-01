"""FameGrid Auto Color for Forge Neo -- Extras tab postprocessing operation.

Grades an already-existing image via the Extras tab / batch-from-directory
pipeline. Independent of scripts/famegrid_auto_color.py (the txt2img/img2img
accordion) -- if both are enabled for the same run (via Settings >
Postprocessing > "Enable Postprocessing operations in txt2img and img2img"),
the correction is applied twice.
"""

import gradio as gr

from modules import scripts, scripts_postprocessing
from modules.ui_components import InputAccordion

from lib_famegrid.adapter import apply
from lib_famegrid.loader import load_corrector_class
from lib_famegrid.params import to_infotext, to_node_kwargs

_FameGridAutoColorCorrector = load_corrector_class(scripts.basedir())
_corrector = _FameGridAutoColorCorrector()


class ScriptPostprocessingFameGridAutoColor(scripts_postprocessing.ScriptPostprocessing):
    name = "FameGrid Auto Color"
    order = 3000

    def ui(self):
        node_defaults = _FameGridAutoColorCorrector.INPUT_TYPES()["required"]

        def default(name):
            return node_defaults[name][1]["default"]

        with InputAccordion(False, label=self.name) as enable:
            gr.HTML(
                "Deterministic per-image auto color correction: white balance, "
                "contrast, saturation, and a manual finishing grade."
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

        return {
            "enable": enable,
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

    def process(
        self,
        pp: scripts_postprocessing.PostprocessedImage,
        enable=False,
        auto_color=True,
        auto_color_strength=0.8,
        correct_contrast=True,
        contrast_clip_percent=7.3,
        normalize_saturation=True,
        saturation_strength=0.15,
        protect_skin=True,
        preserve_hue=True,
        shadow_depth=0.5,
        highlight_rolloff=0.0,
        brightness=0.1,
        shadows=-0.15,
        highlights=-0.05,
        saturation=0.0,
        vibrance=-0.20,
    ):
        if not enable:
            return

        values = dict(
            auto_color=auto_color,
            auto_color_strength=auto_color_strength,
            correct_contrast=correct_contrast,
            contrast_clip_percent=contrast_clip_percent,
            normalize_saturation=normalize_saturation,
            saturation_strength=saturation_strength,
            protect_skin=protect_skin,
            preserve_hue=preserve_hue,
            shadow_depth=shadow_depth,
            highlight_rolloff=highlight_rolloff,
            brightness=brightness,
            shadows=shadows,
            highlights=highlights,
            saturation=saturation,
            vibrance=vibrance,
        )

        pp.image = apply(_corrector, pp.image, **to_node_kwargs(values))
        pp.info.update(to_infotext(values))
