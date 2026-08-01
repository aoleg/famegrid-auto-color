# Changelog

All notable changes to FameGrid Auto Color are documented here.

## 1.2.0 - 2026-08-01

Fixes blown, yellow-shifted highlights on bright saturated subjects — sunlit
skin most visibly. **Output changes for existing workflows at default
settings.**

- Added `preserve_hue` (default `true`). The endpoint curves are now driven
  from luminance with all three channels scaled by a common gain, so the
  stretch cannot rotate hue, and highlights roll off through a smooth shoulder
  instead of being clamped. Set it to `false` for the previous per-channel
  behavior.
- The previous per-channel stretch let the brightest channel clip on its own.
  On skin, red saturated first and the highlight drifted yellow before
  collapsing to a flat, detail-free plateau. Measured on a sample portrait at
  the old defaults, ~10% of the hand was pegged at an achromatic ceiling with
  a 16.7 degree hue shift; the same image now shows no plateau.
- Applied the same hue-preserving rolloff to the `white_balance_power = 0`
  fallback stretch, which had neither robust anchors nor a strength blend and
  was measurably more damaging than the main path.
- Changed `contrast_clip_percent` default from `7.3` to `0.1`. The old value
  drove roughly 12% of a typical image into the clamp; conventional auto-levels
  clips well under 1%.
- Changed `auto_color_strength` default from `1.1` to `0.8`. Values above `1.0`
  extrapolate past the computed correction rather than blending toward it.
- Changed `brightness` default from `0.1` to `0.0`. Its gain scales with how
  dark a pixel already is, so `0.1` raised the black point by ~10 levels while
  moving highlights by ~2 — a shadow lift that partly undid the endpoint
  correction and overrode the preset's own `shadows = -0.15`.
- The hue-preserving shoulder is a no-op on images that never exceed `1.0`, so
  enabling it cannot dim near-white content that was already in range.
- Replaced the hard percentile endpoint stretch on the per-channel path with a
  continuous, endpoint-preserving three-segment curve, so shadow and highlight
  tail values stay distinct instead of flattening to black or white, and capped
  that path's effective blend at `1.0` to stop over-strength extrapolation from
  creating new clipping. Contributed by Miguel (`76dfaf27`); on the
  hue-preserving path the shoulder handles overshoot, so strength above `1.0`
  remains meaningful there.

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
