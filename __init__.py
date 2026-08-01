from .node import FameGridAutoColorCorrector


NODE_CLASS_MAPPINGS = {
    "FameGridAutoColorCorrector": FameGridAutoColorCorrector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FameGridAutoColorCorrector": "Auto Color Corrector (FameGrid)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
