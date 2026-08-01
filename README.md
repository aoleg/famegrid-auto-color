# FameGrid Auto Color

FameGrid Auto Color is a deterministic image → image color correction for
removing global color casts, setting robust tonal endpoints, normalizing
unusual saturation, and applying a small manual finishing grade.

It analyzes every input image independently. There is no AI model, prompt,
reference image, network request, or fixed color look. The result is calculated
from the pixels in the current image and is repeatable for the same input and
settings.

This single repository ships two things sharing one implementation
([node.py](node.py)):

- **A ComfyUI custom node** -- `FameGrid → Color → Auto Color Corrector (FameGrid)`.
- **A Forge Neo extension** (`sd-webui-forge-classic`, neo branch) -- a
  txt2img/img2img accordion, an Extras-tab operation, and X/Y/Z Plot support.

Installing for one target also installs the files for the other (they're
inert under the platform that doesn't use them) -- see
[Installation](#installation) for both.

## Features

- Automatic color-cast correction from image statistics
- Full-range-preserving shadow and highlight endpoint curves
- Likely-neutral midtone correction with false-neutral safeguards
- Automatic contrast and conservative saturation normalization
- Manual brightness, shadows, highlights, saturation, and vibrance
- Reduced saturation and vibrance changes on skin hues
- Independent analysis of every image in a batch
- Native float32 processing inside ComfyUI
- Preservation of extra channels such as alpha
- No third-party Python dependencies beyond the PyTorch bundled with ComfyUI / Forge
- Forge Neo: txt2img/img2img accordion, Extras-tab operation, X/Y/Z Plot axes,
  and infotext round-tripping (paste a prior generation's parameters back in)

## Installation

### ComfyUI

**ComfyUI Manager** -- use **Install via Git URL** and enter:

```text
https://github.com/ultramuseart/famegrid-auto-color.git
```

**Manual installation** -- from your ComfyUI installation:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/ultramuseart/famegrid-auto-color.git
```

Restart ComfyUI. No separate `pip install` step is required. To update later:

```bash
cd ComfyUI/custom_nodes/famegrid-auto-color
git pull
```

Add a node and navigate to `FameGrid → Color → Auto Color Corrector (FameGrid)`.
Connect an `IMAGE` input and use the returned `IMAGE` anywhere downstream.

### Forge Neo (sd-webui-forge-classic)

From your Forge Neo installation:

```bash
cd extensions
git clone https://github.com/ultramuseart/famegrid-auto-color.git
```

Restart Forge Neo (or use **Installed** > **Check for updates** > **Apply and
restart UI**). No separate `pip install` step is required -- the extension
uses only `torch` and `Pillow`, both already bundled with Forge Neo. To
update later:

```bash
cd extensions/famegrid-auto-color
git pull
```

See [Using it in Forge Neo](#using-it-in-forge-neo) below for where the
controls show up.

## Using it in Forge Neo

The extension adds the same 12 grading controls in two places:

- **txt2img / img2img** -- a **FameGrid Auto Color** accordion (collapsed and
  disabled by default). Grades every generated image just before it's saved,
  after any inpaint-overlay compositing. Settings are recorded in the image's
  infotext (`FameGrid AC ...` keys) so a later "send to txt2img" / drag-and-drop
  of the PNG restores them.
- **Extras tab** -- the same controls as a postprocessing operation, for
  grading images you already have (also available for
  batch-from-directory). Its own accordion, independent of the txt2img/img2img
  one.

Enabling both for the same run applies the correction twice -- pick one, or
deliberately double up if that's the look you want.

**X/Y/Z Plot**: every control is available as an axis (`FameGrid AC Enable`,
`FameGrid AC Auto Color Strength`, `FameGrid AC Brightness`, etc.), so you can
sweep e.g. `auto_color_strength` or `vibrance` across a grid the same way you
would `CFG Scale` or `Steps`.

**Auto color curves checkbox**: node.py's `white_balance_power` (`0`-`20`)
is a legacy compatibility control where only "0" vs. "greater than 0" matters
(see [Recommended defaults](#recommended-defaults) below). The Forge UI
surfaces this as a single **Auto color curves** checkbox rather than the
0-20 slider; enabling it is equivalent to `white_balance_power = 8`.

Two things worth knowing about the Forge integration specifically:

- The txt2img/img2img accordion grades the image **after** inpaint-overlay
  compositing, so an inpaint job re-grades the whole frame, including pixels
  pasted back from the original -- not just the inpainted region.
- Forge decodes to 8-bit before this hook runs, so aggressive curves can band
  more visibly than the same settings would in ComfyUI's float32 pipeline.

## Recommended defaults

The published defaults are the current FameGrid finishing preset:

| Control | Default | What it does |
| --- | ---: | --- |
| `white_balance_power` | `8` | Legacy compatibility control. `0` disables auto color; any value above `0` enables Auto Color Curves. |
| `auto_color_strength` | `0.80` | Blends the adaptive color and endpoint correction. Values above `1.0` extrapolate past the computed correction; with `preserve_hue` off that extrapolation is capped at `1.0` to avoid creating clipping. |
| `correct_contrast` | `true` | Enables robust endpoint contrast as part of the color curves. |
| `contrast_clip_percent` | `0.1` | Histogram tail used to form the shadow and highlight anchors. The effective tail is floored at `0.5%`. |
| `normalize_saturation` | `true` | Corrects only images outside the conservative saturation band. |
| `saturation_strength` | `0.15` | Strength of automatic saturation normalization. |
| `protect_skin` | `true` | Reduces automatic saturation and manual vibrance changes on skin hues. |
| `preserve_hue` | `true` | Drives the endpoint curves from luminance and scales all three channels together, so highlights roll off without rotating hue. |
| `brightness` | `0.00` | Global brightness. Negative darkens; positive brightens. Weighted toward the shadow end, so positive values lift the black point. |
| `shadows` | `-0.15` | Negative deepens shadows; positive lifts them. |
| `highlights` | `-0.05` | Negative lowers highlights; positive raises them. |
| `saturation` | `0.00` | Global saturation. `-1` produces grayscale; positive values boost color. |
| `vibrance` | `-0.35` | Targets muted colors more strongly than colors that are already saturated. |

Manual grading controls range from `-1` to `1`.

## How it works

### 1. Analyze each image separately

Each batch item is sampled and analyzed independently. Statistics from one image
never alter another image in the batch.

### 2. Estimate robust color endpoints

The node calculates luminance and builds shadow and highlight color anchors from
the configured histogram tails. Averaging groups of pixels is less sensitive to
a single clipped pixel than using raw minimum and maximum values.

With `preserve_hue` enabled (the default), the curve passes continuously
through true black, the shadow anchor, the highlight anchor, and true white,
so values outside the anchors stay distinct rather than clamping flat. It runs
on luminance and scales all three channels by the resulting gain, so the
correction is purely tonal and cannot change hue.

This matters on bright saturated subjects, sunlit skin most of all. Scaling
each channel against its own anchor and clamping at `1.0` lets the brightest
channel saturate while the others keep climbing — on skin, red saturates first
and the highlight drifts yellow, then flattens into a detail-free plateau.
Disabling `preserve_hue` restores that pre-1.2 per-channel behavior.

With `preserve_hue` disabled, separate RGB curves instead pass continuously
through true black, the estimated shadow anchor, the estimated highlight anchor,
and true white. That keeps each channel's own endpoint neutralization and leaves
pixels beyond the anchors distinct rather than clipped, but because the anchors
keep their original luminance it performs little tonal expansion.

Images without enough tonal evidence skip the correction instead of collapsing
flat frames.

### 3. Find a likely-neutral midtone

Pixels in a safe midtone range are ranked by chroma. The lowest-chroma group is
treated as a possible neutral reference and weighted toward useful middle values.
A per-channel gamma curve moves that reference toward neutral gray.

The correction is skipped when the image does not contain enough neutral-color
evidence. This guard helps preserve intentionally monochromatic or solid-color
images.

### 4. Normalize saturation conservatively

Automatic saturation does nothing when average saturation is already within the
healthy target band. Washed-out and clearly oversaturated images are moved only
partway toward the band, controlled by `saturation_strength`. Skin-hue pixels
receive a reduced adjustment when protection is enabled.

### 5. Apply the manual finishing grade

Brightness applies across the full frame, but its gain scales with how dark a
pixel already is, so positive values lift the black point rather than shifting
everything evenly — a small positive value can visibly wash out shadows and
work against the endpoint correction. Shadows and highlights use smooth
luminance-weighted masks, while saturation changes all colors uniformly.
Vibrance weights its effect by current saturation, so muted colors move more and
already-strong colors move less. All operations remain bounded to ComfyUI's
`0–1` image range.

## Processing precision

ComfyUI `IMAGE` tensors are processed as float32 RGB values. The node converts
the first three channels to float32 for correction, restores the input tensor's
original dtype on output, and passes any additional channels through unchanged.

The node does not change the file format used by downstream save nodes. Choose a
16-bit or floating-point format in your output workflow when you need additional
grading latitude.

## Practical guidance

- Start with the defaults and reduce `auto_color_strength` if a correction feels
  too assertive.
- `contrast_clip_percent` selects the shadow and highlight groups used for
  analysis. Raise it for a more assertive stretch; large values push a
  correspondingly large share of the image toward pure black and white.
- Leave `preserve_hue` on unless you specifically want the per-channel look; it
  has no cost on images that never overshoot, and it is what keeps bright skin
  from going yellow and flat. Turn it off for endpoint colour neutralization
  with minimal tonal change.
- Set `white_balance_power` to `0` to bypass auto color while retaining optional
  contrast and manual grading.
- Keep `protect_skin` enabled for portraits unless you intentionally want a full
  global color treatment.
- Use manual saturation for a uniform change and vibrance when muted colors need
  a more selective adjustment.

## Limitations

- This is a global correction, not a semantic or locally masked grade.
- Any deterministic neutral estimator can be ambiguous when a scene contains no
  credible neutral colors or is intentionally dominated by one hue.
- Clipped source channels cannot be reconstructed, but the node avoids creating
  new endpoint clipping in its automatic technical curve.
- The node does not convert color spaces or attach ICC profiles; it operates on
  the RGB values supplied by ComfyUI or Forge.
- In Forge Neo, the txt2img/img2img accordion grades the whole composited
  frame (see [Using it in Forge Neo](#using-it-in-forge-neo)), and enabling
  both the accordion and the Extras-tab operation for the same run applies
  the correction twice.
- `preserve_hue` keeps the endpoint stretch from rotating hue, but the
  neutral-midtone gamma is a color correction by design and will still shift
  hue when it finds a cast to remove.

## Validation

The included tests verify the published defaults, tensor shape and range,
batch independence, alpha preservation, and bounded manual controls
(`node.py`); the PIL/tensor bridge (`lib_famegrid/adapter.py`); and, via an
offline stub harness that fakes the relevant pieces of Forge's `modules`
package and `gradio` without needing a real Forge/gradio install, both Forge
scripts and the X/Y/Z Plot integration:

```bash
python -m unittest discover -s tests -v
```

The Forge Neo integration was also smoke-tested against a real
`sd-webui-forge-classic` instance (`--ui-debug-mode`, no checkpoint needed):
both accordions (txt2img and img2img), the Extras-tab operation, and all 13
X/Y/Z Plot axes registered correctly with no duplicates and no console/log
errors. That run doesn't cover actual pixel correctness or the infotext
round-trip, since both need a real checkpoint and an actual generation.

## Project files

```text
famegrid-auto-color/
├── __init__.py                        # ComfyUI node registration
├── node.py                            # shared correction math (ComfyUI node + Forge scripts)
├── lib_famegrid/
│   ├── loader.py                      # loads node.py into the Forge scripts
│   ├── adapter.py                     # PIL <-> ComfyUI IMAGE tensor bridge
│   ├── params.py                      # shared field list / infotext labels / node.py kwarg mapping
│   └── xyz.py                         # X/Y/Z Plot axis support
├── scripts/
│   ├── famegrid_auto_color.py         # Forge Neo: txt2img/img2img accordion
│   └── famegrid_auto_color_extras.py  # Forge Neo: Extras tab operation
├── tests/
│   ├── test_node.py
│   ├── test_adapter.py
│   ├── test_xyz.py
│   ├── test_forge_scripts.py
│   ├── test_forge_extras_script.py
│   └── forge_stubs.py                 # shared fakes used by the test_forge_*.py files
├── CHANGELOG.md
└── README.md
```

## Creator Studio AI by UltraMuse

Creator Studio AI is UltraMuse's connected production studio for AI influencer
content. It brings image and video generation, identity-preserving swaps,
editing, upscaling, post-processing, captions, UGC campaigns, publishing, and
custom ComfyUI workflow imports into one workspace. Bring an existing character
or reference set, keep assets and production history organized, and move from an
idea to finished content without rebuilding the workflow across separate tools.

Learn more: **[www.ultramuse.art/creatorstudio](https://www.ultramuse.art/creatorstudio)**
