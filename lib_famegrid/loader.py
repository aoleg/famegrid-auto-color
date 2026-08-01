"""Load famegrid-auto-color's node.py as a shared module.

node.py lives at the extension root and has no ComfyUI-specific imports (only
torch), so it works unmodified both as the ComfyUI node and as the shared math
behind the Forge Neo scripts in this repo. It is loaded via
`importlib.util.spec_from_file_location` under a private sys.modules key so it
never collides with another installed extension's own node.py of the same
bare filename.
"""

from __future__ import annotations

import importlib.util
import os
import sys

_MODULE_NAME = "famegrid_auto_color_node"
_cached_module = None


def load_node_module(extension_root: str):
    """Import node.py from `extension_root`, caching the result.

    `extension_root` should be captured via `scripts.basedir()` at the calling
    script's own module-import time. `scripts.basedir()` reflects whichever
    script Forge is currently loading and is not reliable to call later, e.g.
    from inside a UI callback.
    """
    global _cached_module
    if _cached_module is not None:
        return _cached_module

    node_path = os.path.join(extension_root, "node.py")
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, node_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)

    _cached_module = module
    return module


def load_corrector_class(extension_root: str):
    """Return the FameGridAutoColorCorrector class from node.py."""
    return load_node_module(extension_root).FameGridAutoColorCorrector
