# Changelog

All notable changes to FameGrid Auto Color are documented here.

## 1.2.4 - 2026-08-01

- The shadow tail now uses a derived target with a bounded slope, matching what
  1.2.3 did for highlights. A fixed absolute target of 0.005 against a shadow
  anchor at 0.061 was a 12x crush: the darkest decile lost a third of its
  distinct levels (57 to 33 on a test frame) and the 5th percentile fell well
  below the ungraded source. At the new 0.5 the graded 5th percentile lands
  within a few levels of source across the test set (35.7 against 38.7, 30.6
  against 30.3, 24.8 against 21.0).
- Both tails are now symmetric in form: each has a compression factor fixing
  its segment slope wherever the anchors land, rather than a fixed slice of
  output range whose severity depends on anchor position.
- Note the inherent trade. Midtone expansion is bought by compressing a tail,
  so with highlights passing through untouched the shadow setting alone
  controls how much tonal work the curve does. Relaxing the shadow compression
  to protect blacks costs a little face modelling (about 2-4% of relative form
  contrast at the shipped values); tightening it recovers that and crushes
  shadows again.

## 1.2.3 - 2026-08-01

- Highlights now pass through the endpoint curve untouched by default
  (`highlight_compression` 1.0), so the correction only deepens shadows and
  expands midtones. Even the bounded 0.7 compression shipped in 1.2.1 was
  visible: about a quarter of a portrait's skin sits above the highlight
  anchor, and compressing it cost a hand 11.8% of its relative form contrast
  and the cheeks 3.8%. Every measured region is now at or above the ungraded
  source (hand -0.9%, cheeks +1.5 to +1.9%, forehead +1.1%).
- Lowering `contrast_clip_percent` does not help this and makes it worse: the
  larger tail is what supplies the midtone expansion the face sits in. At clip
  0.1 the same regions measure -7.0 to -11.6% regardless of compression.
- Net contrast on a bright, high-key frame is now close to ungraded (171.2
  against 172.1) since the tonal work is confined to shadows and midtones; a
  more typical frame still gains (162.5 against 152.3).

## 1.2.2 - 2026-08-01

- Manual brightness/shadows/highlights no longer desaturate. They added the
  same offset to every channel, which raises `max` while leaving `max - min`
  and so lowers saturation — hardest in the darker, more saturated regions
  that carry facial modelling. The default `brightness = 0.1` alone cost a
  test portrait's face 12% of its saturation and read as a flattened nose,
  even though its luminance contrast was intact. With `preserve_hue` the move
  is now computed on luminance and applied as a common gain, holding R:G:B
  ratios exactly: face saturation loss drops from 11.9% to 4.3%, and an
  earlier portrait's hand recovers 0.232 to 0.261 against an ungraded 0.282.
- That gain diverges as luminance approaches zero, so below a chroma floor —
  where chroma is quantisation noise rather than signal — it blends back to
  the additive form rather than amplifying it. Deep-shadow high-frequency
  energy is unchanged (4.94 against the ungraded 4.98).

## 1.2.1 - 2026-08-01

- The endpoint curve's highlight segment now holds a bounded slope instead of
  mapping the whole above-anchor tail into a fixed slice of the output range.
  At the default `contrast_clip_percent` that slice was ~2% — an ~11x squeeze —
  so bright subjects sitting above the anchor lost their tonal separation and
  read as blown out without a single pixel clipping. Measured on a portrait in
  a pale knit sweater, 14.2% of the face and 9.0% of the sweater fell in that
  zone; face tonal spread recovers from 30.2 to 41.5 against the ungraded 48.1,
  and an earlier test portrait's hand from 39.1 to 53.1 against 54.7.
- Changed `vibrance` default from `-0.35` to `-0.20`. Vibrance targets muted
  colors hardest, so pale low-saturation garments took the brunt of it; this
  accounted for roughly a quarter of the desaturation seen on that sweater.
- Neither change affects clipping, which remains at 0.00% on both ends for the
  published defaults.
- Fixed the Forge Neo loader caching `node.py` permanently for the life of the
  process. Forge's "Reload UI" re-executes `scripts/*.py` but leaves
  `lib_famegrid` in `sys.modules`, so after a `git pull` the extension kept
  running whatever `node.py` was on disk at startup — an update appeared to do
  nothing until the whole process was restarted. The cache is now keyed on
  `node.py`'s mtime and size.
- The one-shot diagnostic line now reports `node.py`'s timestamp and size, so
  the live build is identifiable from the console.

## 1.2.0 - 2026-08-01

Fixes blown, yellow-shifted highlights on bright saturated subjects — sunlit
skin most visibly. **Output changes for existing workflows at default
settings.**

- Added `preserve_hue` (default `true`). The endpoint curve is a continuous
  three-segment map through black, the shadow anchor, the highlight anchor, and
  white, driven from luminance with all three channels scaled by a common gain
  — so tail values stay distinct, the midtones genuinely stretch, and the
  correction cannot rotate hue. Set it to `false` for per-channel endpoint
  neutralization with minimal tonal change.
- The previous per-channel stretch let the brightest channel clip on its own.
  On skin, red saturated first and the highlight drifted yellow before
  collapsing to a flat, detail-free plateau. Measured on a sample portrait at
  the old defaults, ~10% of the hand was pegged at an achromatic ceiling with
  a 16.7 degree hue shift; the same image now shows no plateau.
- Applied the same hue-preserving rolloff to the `white_balance_power = 0`
  fallback stretch, which had neither robust anchors nor a strength blend and
  was measurably more damaging than the main path.
- Changed `auto_color_strength` default from `1.1` to `0.8`. Values above `1.0`
  extrapolate past the computed correction rather than blending toward it.
  `contrast_clip_percent` and `brightness` keep their published values: once
  the curve no longer clamps, `7.3` is no longer destructive, and the `+0.1`
  brightness lift is what keeps its aggressive shadow compression off the floor.
  On the sample portrait these defaults now clip nothing at either end — 0.00%
  of pixels pinned at black or white — while raising contrast from 152.3 to
  186.1 and holding highlight hue to within 1.7 degrees.
- The hue-preserving shoulder is a no-op on images that never exceed `1.0`, so
  enabling it cannot dim near-white content that was already in range.
- Replaced the hard percentile endpoint stretch on the per-channel path with a
  continuous, endpoint-preserving three-segment curve, so shadow and highlight
  tail values stay distinct instead of flattening to black or white, and capped
  that path's effective blend at `1.0` to stop over-strength extrapolation from
  creating new clipping. Contributed by Miguel (`76dfaf27`); on the
  hue-preserving path the shoulder handles overshoot, so strength above `1.0`
  remains meaningful there. That curve shape is also what the hue-preserving
  path now uses, applied to luminance and with targets chosen to expand
  contrast rather than hold the anchors at their own brightness — on a sample
  portrait this cut crushed shadow pixels roughly threefold while keeping the
  tonal expansion the per-channel form gives up.

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
