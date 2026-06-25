from enum import Enum


class InterpolationMode(Enum):
    NEAREST = "nearest"
    NEAREST_EXACT = "nearest_exact"
    BOX = "box"
    BILINEAR = "bilinear"
    HAMMING = "hamming"
    BICUBIC = "bicubic"
    LANCZOS = "lanczos"
