# FameGrid Auto Color for ComfyUI

FameGrid Auto Color is a deterministic `IMAGE → IMAGE` ComfyUI node for removing
global color casts, setting robust tonal endpoints, normalizing unusual
saturation, and applying a small manual finishing grade.

It analyzes every input image independently. There is no AI model, prompt,
reference image, network request, or fixed color look. The result is calculated
from the pixels in the current image and is repeatable for the same input and
settings.

## Features

- Automatic color-cast correction from image statistics
- Full-range-preserving shadow and highlight endpoint curves
- Likely-neutral midtone correction with false-neutral safeguards
- Automatic contrast and conservative saturation normalization
- Manual brightness, shadows, highlights, saturation, and vibrance
- Reduced saturation and vibrance changes on skin hues
- Independent analysis of every image in a ComfyUI batch
- Native float32 processing inside ComfyUI
- Preservation of extra channels such as alpha
- No third-party Python dependencies beyond the PyTorch bundled with ComfyUI

## Installation

### ComfyUI Manager

Use **Install via Git URL** and enter:

```text
https://github.com/ultramuseart/famegrid-auto-color.git
```

Restart ComfyUI after installation.

### Manual installation

From your ComfyUI installation:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/ultramuseart/famegrid-auto-color.git
```

Restart ComfyUI. No separate `pip install` step is required.

To update later:

```bash
cd ComfyUI/custom_nodes/famegrid-auto-color
git pull
```

## Finding the node

Add a node and navigate to:

```text
FameGrid → Color → Auto Color Corrector (FameGrid)
```

Connect an `IMAGE` input and use the returned `IMAGE` anywhere downstream.

## Recommended defaults

The published defaults are the current FameGrid finishing preset:

| Control | Default | What it does |
| --- | ---: | --- |
| `white_balance_power` | `8` | Legacy compatibility control. `0` disables auto color; any value above `0` enables Auto Color Curves. |
| `auto_color_strength` | `1.10` | Blends the adaptive color and endpoint correction. The technical curve caps its effective blend at `1.0` to avoid creating clipping. |
| `correct_contrast` | `true` | Enables robust endpoint contrast as part of the color curves. |
| `contrast_clip_percent` | `7.3` | Percentage used to form robust shadow and highlight color groups. |
| `normalize_saturation` | `true` | Corrects only images outside the conservative saturation band. |
| `saturation_strength` | `0.15` | Strength of automatic saturation normalization. |
| `protect_skin` | `true` | Reduces automatic saturation and manual vibrance changes on skin hues. |
| `brightness` | `0.10` | Global brightness. Negative darkens; positive brightens. |
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

When sufficient channel range exists, separate RGB curves pass continuously
through true black, the estimated shadow anchor, the estimated highlight anchor,
and true white. Pixels beyond the robust anchors remain distinct instead of being
flattened into clipped black or white plateaus. Images without enough tonal
evidence skip the correction instead of collapsing flat frames.

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

Brightness affects the full frame. Shadows and highlights use smooth
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
- `contrast_clip_percent` selects the shadow and highlight groups used for analysis;
  it no longer discards those histogram tails.
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
  the RGB values supplied by ComfyUI.

## Validation

The included tests verify the published defaults, tensor shape and range, batch
independence, alpha preservation, and bounded manual controls:

```bash
python -m unittest discover -s tests -v
```

## Project files

```text
famegrid-auto-color/
├── __init__.py
├── node.py
├── tests/
│   └── test_node.py
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
