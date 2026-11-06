"""Image loading, letterboxing, cropping, and shared drawing helpers."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageFont, ImageOps

from .constants import PAPER

FONT_PATHS = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "DejaVuSans.ttf",
]
SYMBOL_FONT_PATHS = [r"C:\Windows\Fonts\seguisym.ttf"] + FONT_PATHS
SYMBOL_TEST = "\u265a"


def font(size: int, symbol: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A usable TrueType font, falling back to Pillow's bundled default."""
    for path in SYMBOL_FONT_PATHS if symbol else FONT_PATHS:
        try:
            f = ImageFont.truetype(path, size)
            if symbol and not f.getmask(SYMBOL_TEST).getbbox():
                continue
            return f
        except (OSError, ValueError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 has no size argument
        return ImageFont.load_default()


def load_rgb(path: str | Path) -> Image.Image:
    with Image.open(path) as opened:
        im = ImageOps.exif_transpose(opened)
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, PAPER + (255,))
            im = Image.alpha_composite(bg, im)
        return im.convert("RGB")


def _json_default(obj):
    """Allow numpy scalars and arrays in reports without importing numpy here."""
    if hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def save_json(path: str | Path, obj: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False,
                               default=_json_default), encoding="utf-8")


def clamp_bbox(bbox: Sequence[float], width: int,
               height: int) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in bbox)
    x0, x1 = sorted((max(0.0, min(x0, width)), max(0.0, min(x1, width))))
    y0, y1 = sorted((max(0.0, min(y0, height)), max(0.0, min(y1, height))))
    if x1 - x0 < 2 or y1 - y0 < 2:
        raise ValueError(f"board box is empty after clamping: {bbox!r}")
    return x0, y0, x1, y1


def letterbox(im: Image.Image, size: int = 640, pad: int = 114
              ) -> tuple[Image.Image, float, int, int]:
    """Resize into a square canvas. Returns canvas, scale, x-pad, y-pad."""
    w, h = im.size
    if w <= 0 or h <= 0:
        raise ValueError("empty image")
    scale = min(size / w, size / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (pad, pad, pad))
    pad_x, pad_y = (size - nw) // 2, (size - nh) // 2
    canvas.paste(resized, (pad_x, pad_y))
    return canvas, scale, pad_x, pad_y


def estimate_skew(im: Image.Image, max_angle: float = 4.0, step: float = 0.5) -> float:
    """Return a small rotation (degrees, PIL convention) that best aligns page lines."""
    gray = np.asarray(im.convert("L"), dtype=np.uint8)
    h, w = gray.shape
    scale = min(1.0, 900.0 / max(w, h))
    if scale < 1.0:
        gray = np.asarray(Image.fromarray(gray).resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.BILINEAR), dtype=np.uint8)
    base = Image.fromarray(gray)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + 1e-9, step):
        rotated = np.asarray(base.rotate(float(angle), resample=Image.Resampling.BILINEAR,
                                         expand=False, fillcolor=255), dtype=np.float32)
        col = np.abs(np.diff(rotated, axis=1)).sum(axis=0)
        row = np.abs(np.diff(rotated, axis=0)).sum(axis=1)
        score = float(np.sort(col)[-15:].mean() + np.sort(row)[-15:].mean())
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def rotate_working(im: Image.Image, angle: float) -> Image.Image:
    if abs(angle) < 1e-6:
        return im
    return im.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=PAPER)


def normalized_board(im: Image.Image, bbox: Sequence[float], flip: bool) -> Image.Image:
    """Crop the board and rotate it so White is at the bottom."""
    crop = im.crop(tuple(int(round(v)) for v in bbox))
    if flip:
        crop = crop.transpose(Image.Transpose.ROTATE_180)
    return crop


def crop_with_margin(im: Image.Image, bbox: Sequence[float], margin: float,
                     flip: bool = False) -> tuple[Image.Image, tuple[float, float], float, float]:
    """Crop ``bbox`` plus a relative margin, optionally rotating 180 degrees.

    Returns ``(crop, origin, board_w, board_h)`` where ``origin`` is the
    top-left corner of the (possibly rotated) board inside ``crop``.  Mapping a
    detection centre ``(cx, cy)`` to board-normalized coordinates is then just
    ``(cx - origin[0], cy - origin[1])``.
    """
    x0, y0, x1, y1 = (float(v) for v in bbox)
    bw, bh = x1 - x0, y1 - y0
    left = max(0.0, x0 - margin * bw)
    top = max(0.0, y0 - margin * bh)
    right = min(float(im.width), x1 + margin * bw)
    bottom = min(float(im.height), y1 + margin * bh)
    box = (int(math.floor(left)), int(math.floor(top)),
           int(math.ceil(right)), int(math.ceil(bottom)))
    crop = im.crop(box)
    if flip:
        crop = crop.transpose(Image.Transpose.ROTATE_180)
        origin = (crop.width - (x1 - box[0]), crop.height - (y1 - box[1]))
    else:
        origin = (x0 - box[0], y0 - box[1])
    return crop, origin, bw, bh


def cell_rect(row: int, col: int, width: int, height: int) -> tuple[int, int, int, int]:
    x0 = int(round(col * width / 8.0))
    x1 = int(round((col + 1) * width / 8.0))
    y0 = int(round(row * height / 8.0))
    y1 = int(round((row + 1) * height / 8.0))
    return x0, y0, x1, y1


def square_name(row: int, col: int) -> str:
    return f"{chr(ord('a') + col)}{8 - row}"


def square_index(name: str) -> tuple[int, int]:
    name = name.strip().lower()
    if len(name) != 2 or name[0] not in "abcdefgh" or name[1] not in "12345678":
        raise ValueError(f"bad square {name!r}")
    return 8 - int(name[1]), ord(name[0]) - ord("a")
