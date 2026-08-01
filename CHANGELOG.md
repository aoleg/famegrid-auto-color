# Changelog

All notable changes to FameGrid Auto Color are documented here.

## 1.1.0 - 2026-08-01

- Added a Forge Neo (`sd-webui-forge-classic`) extension alongside the
  existing ComfyUI node, sharing the same correction math in `node.py`
  unmodified.
- txt2img/img2img: a **FameGrid Auto Color** accordion, applied via
  `postprocess_image_after_composite` (grades after inpaint-overlay
  compositing).
- Extras tab: the same controls as a `ScriptPostprocessing` operation.
- X/Y/Z Plot support for all 12 grading controls plus the enable flag.
- Settings recorded in generation infotext (`FameGrid AC ...` keys) with
  paste-from-image support.
- No new third-party dependencies: the Forge integration uses only `torch`
  and `Pillow`, both already bundled with Forge Neo.

## 1.0.0 - 2026-07-31

- Initial standalone ComfyUI release.
- Deterministic, per-image auto color curves.
- Robust shadow and highlight endpoint analysis.
- Likely-neutral midtone correction with confidence guards.
- Automatic contrast and conservative saturation normalization.
- Manual brightness, shadows, highlights, saturation, and vibrance controls.
- Optional skin-hue protection.
- Independent processing for every image in a batch.
- Float32 ComfyUI processing with alpha-channel preservation.
