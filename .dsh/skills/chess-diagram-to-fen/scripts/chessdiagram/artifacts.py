"""Staging and audit images.

Every artifact is deliberately redundant: the cells, the contact sheet, the
detection overlay, the full audit, and four quadrant audits all describe the
same 64 decisions from different angles.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

from .constants import (
    BLACK_PIECE_COLOUR, GRID_RED, LABEL, MUTED, PAPER, REVIEW_COLOUR,
    WHITE_PIECE_COLOUR,
)
from .geometry import CellPrediction
from .imaging import cell_rect, font

WHITE = (255, 255, 255)


def _tag(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
         fnt: ImageFont.ImageFont, fill: tuple[int, int, int],
         bg: tuple[int, int, int] = WHITE, pad: int = 3,
         anchor: str = "la", radius: int = 3) -> None:
    bbox = draw.textbbox(xy, text, font=fnt, anchor=anchor)
    draw.rounded_rectangle(
        [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
        radius=radius, fill=bg)
    draw.text(xy, text, font=fnt, fill=fill, anchor=anchor)


def _frame(w: int, h: int, title: str, margin: tuple[int, int, int, int] = (54, 62, 44, 44)
           ) -> tuple[Image.Image, ImageDraw.ImageDraw, int, int]:
    left, top, right, bottom = margin
    canvas = Image.new("RGB", (w + left + right, h + top + bottom), PAPER)
    draw = ImageDraw.Draw(canvas)
    if title:
        draw.text(((w + left + right) / 2, top - 46), title,
                  font=font(23), fill=(70, 70, 70), anchor="ma")
    return canvas, draw, left, top


def _grid(draw: ImageDraw.ImageDraw, ox: int, oy: int, w: int, h: int,
          colour=GRID_RED) -> None:
    for i in range(9):
        x = ox + i * w / 8
        draw.line([(x, oy), (x, oy + h)], fill=colour, width=1)
        y = oy + i * h / 8
        draw.line([(ox, y), (ox + w, y)], fill=colour, width=1)


def _labels(draw: ImageDraw.ImageDraw, ox: int, oy: int, w: int, h: int,
            fnt: ImageFont.ImageFont) -> None:
    for i in range(8):
        cx = ox + (i + 0.5) * w / 8
        draw.text((cx, oy - 10), chr(ord("a") + i), font=fnt, fill=LABEL, anchor="mb")
        draw.text((cx, oy + h + 10), chr(ord("a") + i), font=fnt, fill=LABEL, anchor="ma")
        cy = oy + (i + 0.5) * h / 8
        draw.text((ox - 10, cy), str(8 - i), font=fnt, fill=LABEL, anchor="rm")
        draw.text((ox + w + 10, cy), str(8 - i), font=fnt, fill=LABEL, anchor="lm")


def _piece_colour(fen: str) -> tuple[int, int, int]:
    if fen == ".":
        return MUTED
    return WHITE_PIECE_COLOUR if fen.isupper() else BLACK_PIECE_COLOUR


def _confidence_colour(conf: float, flagged: bool) -> tuple[int, int, int]:
    if flagged or conf < 0.60:
        return REVIEW_COLOUR
    if conf < 0.80:
        return (210, 150, 40)
    return (40, 140, 80)


def write_overlay(image: Image.Image, boards: Sequence, selected, flip: bool,
                  out: str | Path) -> Path:
    scale = min(1.0, 1600.0 / max(image.size))
    preview = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.Resampling.LANCZOS).convert("RGBA")
    draw = ImageDraw.Draw(preview)
    fnt = font(max(14, int(min(preview.size) / 55)))
    for i, board in enumerate(boards):
        x0, y0, x1, y1 = (v * scale for v in board.bbox)
        chosen = (board is selected or
                  (round(x0, 3), round(y0, 3)) ==
                  (round(selected.bbox[0] * scale, 3), round(selected.bbox[1] * scale, 3)))
        colour = GRID_RED if chosen else (120, 120, 120)
        width = 4 if chosen else 2
        draw.rectangle([x0, y0, x1, y1], outline=colour, width=width)
        _tag(draw, (x0 + 4, y0 + 4), f"board {i}", fnt, WHITE, colour)
        if chosen:
            for k in range(1, 8):
                x = x0 + (x1 - x0) * k / 8
                y = y0 + (y1 - y0) * k / 8
                draw.line([(x, y0), (x, y1)], fill=GRID_RED + (180,), width=1)
                draw.line([(x0, y), (x1, y)], fill=GRID_RED + (180,), width=1)
    text = "selected board in red"
    if flip:
        text += " · rotated 180° for FEN (Black was at the bottom)"
    _tag(draw, (8, 8), text, fnt, WHITE, (40, 40, 40))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    preview.convert("RGB").save(out)
    return out


def write_cells(board: Image.Image, cells: Sequence[CellPrediction],
                review: Sequence[str], out: str | Path, title: str = "") -> Path:
    cell_px = 140
    left, top, right, bottom = 52, 58, 34, 38
    w = 8 * cell_px
    h = 8 * cell_px
    canvas = Image.new("RGB", (w + left + right, h + top + bottom), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw.text(((w + left + right) / 2, 12), title or "64 cells — rank 8 at top, file a at left",
              font=font(22), fill=(70, 70, 70), anchor="ma")
    review_set = set(review)
    for cell in cells:
        x0, y0, x1, y1 = cell.crop
        tile = board.crop((x0, y0, x1, y1)).resize(
            (cell_px, cell_px), Image.Resampling.LANCZOS)
        ox = left + cell.col * cell_px
        oy = top + cell.row * cell_px
        canvas.paste(tile, (ox, oy))
        flagged = cell.square in review_set
        if flagged:
            draw.rectangle([ox + 1, oy + 1, ox + cell_px - 2, oy + cell_px - 2],
                           outline=REVIEW_COLOUR, width=3)
        draw.rectangle([ox, oy, ox + cell_px - 1, oy + cell_px - 1],
                       outline=(210, 210, 210), width=1)
        _tag(draw, (ox + 3, oy + 3), cell.square, font(13), WHITE, (70, 70, 70))
        pred = cell.fen if cell.fen != "." else "·"
        _tag(draw, (ox + 4, oy + cell_px - 22),
             f"{pred} {cell.confidence:.2f}", font(13), WHITE,
             _piece_colour(cell.fen))
    _labels(draw, left, top, w, h, font(19))
    _grid(draw, left, top, w, h)
    draw.rectangle([left, top, left + w, top + h], outline=GRID_RED, width=2)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def write_detection(board: Image.Image, cells: Sequence[CellPrediction],
                    out: str | Path, title: str = "") -> Path:
    size = 8 * 180
    big = board.resize((size, size), Image.Resampling.LANCZOS)
    canvas, draw, left, top = _frame(size, size, title or
                                     "model detections — boxes before square assignment")
    canvas.paste(big, (left, top))
    fnt = font(13)
    for cell in cells:
        for cand in cell.candidates:
            x0, y0, x1, y1 = cand.box
            sx = size / board.width
            sy = size / board.height
            box = [left + x0 * sx, top + y0 * sy, left + x1 * sx, top + y1 * sy]
            colour = _piece_colour(cand.fen)
            draw.rectangle(box, outline=colour, width=2)
            label = f"{cand.fen} {cand.conf:.2f}"
            _tag(draw, (box[0] + 1, box[1] + 1), label, fnt, WHITE, colour, pad=1)
    _grid(draw, left, top, size, size)
    _labels(draw, left, top, size, size, font(20))
    draw.rectangle([left, top, left + size, top + size], outline=GRID_RED, width=3)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def _audit_canvas(board: Image.Image, cells: Sequence[CellPrediction],
                  review: Sequence[str], cell_px: int, fx: int, fy: int,
                  title: str) -> Image.Image:
    cols = rows = 4
    left, top, right, bottom = 58, 66, 38, 44
    w, h = cols * cell_px, rows * cell_px
    canvas = Image.new("RGB", (w + left + right, h + top + bottom), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw.text(((w + left + right) / 2, 12), title, font=font(22),
              fill=(70, 70, 70), anchor="ma")
    review_set = set(review)
    # The quadrant source rectangle in board pixels.
    bw, bh = board.width / 8.0, board.height / 8.0
    x0 = int(round(fx * 4 * bw))
    y0 = int(round(fy * 4 * bh))
    tile = board.crop((x0, y0, int(round(x0 + 4 * bw)), int(round(y0 + 4 * bh))))
    tile = tile.resize((w, h), Image.Resampling.LANCZOS)
    canvas.paste(tile, (left, top))
    for cell in cells:
        if not (fx * 4 <= cell.col < fx * 4 + 4 and fy * 4 <= cell.row < fy * 4 + 4):
            continue
        ox = left + (cell.col - fx * 4) * cell_px
        oy = top + (cell.row - fy * 4) * cell_px
        flagged = cell.square in review_set
        if flagged:
            draw.rectangle([ox + 2, oy + 2, ox + cell_px - 3, oy + cell_px - 3],
                           outline=REVIEW_COLOUR, width=4)
        char = cell.fen if cell.fen != "." else "·"
        colour = _piece_colour(cell.fen)
        tag_size = max(20, int(cell_px * 0.16))
        _tag(draw, (ox + 4, oy + 4), char, font(tag_size),
             WHITE if cell.fen == "." else colour,
             (245, 245, 245) if cell.fen == "." else WHITE, pad=2)
        _tag(draw, (ox + cell_px - 5, oy + cell_px - 5),
             f"{cell.confidence:.2f}", font(max(11, tag_size // 2)),
             WHITE, _confidence_colour(cell.confidence, flagged), pad=1, anchor="rs")
    # quadrant edge labels
    for i in range(5):
        x = left + i * cell_px
        y = top + i * cell_px
        if i < 4:
            draw.text((x + cell_px / 2, top - 10), chr(ord("a") + fx * 4 + i),
                      font=font(19), fill=LABEL, anchor="mb")
            draw.text((x + cell_px / 2, top + h + 10), chr(ord("a") + fx * 4 + i),
                      font=font(19), fill=LABEL, anchor="ma")
            draw.text((left - 10, y + cell_px / 2), str(8 - (fy * 4 + i)),
                      font=font(19), fill=LABEL, anchor="rm")
            draw.text((left + w + 10, y + cell_px / 2), str(8 - (fy * 4 + i)),
                      font=font(19), fill=LABEL, anchor="lm")
    _grid(draw, left, top, w, h)
    draw.rectangle([left, top, left + w, top + h], outline=GRID_RED, width=3)
    return canvas


def _full_audit_canvas(board: Image.Image, cells: Sequence[CellPrediction],
                       review: Sequence[str]) -> Image.Image:
    size = 8 * 180
    left, top, right, bottom = 58, 66, 38, 44
    canvas = Image.new("RGB", (size + left + right, size + top + bottom), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw.text(((size + left + right) / 2, 12),
              "audit — red = White, blue = Black, dot = empty; orange = review",
              font=font(22), fill=(70, 70, 70), anchor="ma")
    big = board.resize((size, size), Image.Resampling.LANCZOS)
    canvas.paste(big, (left, top))
    review_set = set(review)
    for cell in cells:
        ox = left + cell.col * 180
        oy = top + cell.row * 180
        flagged = cell.square in review_set
        if flagged:
            draw.rectangle([ox + 2, oy + 2, ox + 178, oy + 178],
                           outline=REVIEW_COLOUR, width=4)
        char = cell.fen if cell.fen != "." else "·"
        colour = _piece_colour(cell.fen)
        _tag(draw, (ox + 5, oy + 5), char, font(30),
             WHITE if cell.fen == "." else colour,
             (245, 245, 245) if cell.fen == "." else WHITE, pad=2)
        _tag(draw, (ox + 175, oy + 175), f"{cell.confidence:.2f}", font(14),
             WHITE, _confidence_colour(cell.confidence, flagged), pad=1, anchor="rs")
    _labels(draw, left, top, size, size, font(22))
    _grid(draw, left, top, size, size)
    draw.rectangle([left, top, left + size, top + size], outline=GRID_RED, width=3)
    return canvas


def write_audit_file(board: Image.Image, cells: Sequence[CellPrediction],
                     review: Sequence[str], out: str | Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _full_audit_canvas(board, cells, review).save(out)
    return out


def write_audit(board: Image.Image, cells: Sequence[CellPrediction],
                review: Sequence[str], out_dir: str | Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    paths["audit"] = out_dir / "audit.png"
    _full_audit_canvas(board, cells, review).save(paths["audit"])

    for fy in range(2):
        for fx in range(2):
            name = f"audit_q{fy * 2 + fx + 1}"
            q = _audit_canvas(board, cells, review, 280, fx, fy,
                              f"audit {name[-1]} · files {chr(ord('a') + fx * 4)}–"
                              f"{chr(ord('a') + fx * 4 + 3)}, "
                              f"ranks {8 - fy * 4}–{5 - fy * 4}")
            paths[name] = out_dir / f"{name}.png"
            q.save(paths[name])
    return paths


def write_review(board: Image.Image, cells: Sequence[CellPrediction],
                 squares: Sequence[str], out: str | Path) -> Path | None:
    squares = list(dict.fromkeys(squares))
    if not squares:
        return None
    by_square = {c.square: c for c in cells}
    per_row = min(4, max(1, len(squares)))
    tile = 340
    header = 52
    footer = 34
    pad = 14
    rows = math.ceil(len(squares) / per_row)
    w = per_row * (tile + pad) + pad
    h = rows * (tile + header + footer + pad) + pad
    sheet = Image.new("RGB", (w, h), (38, 38, 38))
    draw = ImageDraw.Draw(sheet)
    fnt = font(15)
    for i, sq in enumerate(squares):
        cell = by_square.get(sq)
        if cell is None:
            continue
        row, col = cell.row, cell.col
        # 3x3 context, shifted at the edges so the target is never cropped.
        r0 = max(0, min(row - 1, 5))
        c0 = max(0, min(col - 1, 5))
        x0, y0, x1, y1 = cell_rect(r0, c0, board.width, board.height)
        x2, y2 = cell_rect(r0 + 2, c0 + 2, board.width, board.height)[2:]
        crop = board.crop((x0, y0, x2, y2)).resize((tile, tile), Image.Resampling.LANCZOS)
        sx = tile / (x2 - x0)
        sy = tile / (y2 - y0)
        tx0 = (cell.crop[0] - x0) * sx
        ty0 = (cell.crop[1] - y0) * sy
        tx1 = (cell.crop[2] - x0) * sx
        ty1 = (cell.crop[3] - y0) * sy
        d2 = ImageDraw.Draw(crop)
        d2.rectangle([tx0, ty0, tx1, ty1], outline=REVIEW_COLOUR, width=3)
        px = pad + (i % per_row) * (tile + pad)
        py = pad + (i // per_row) * (tile + header + footer + pad)
        sheet.paste(crop, (px, py + header))
        pred = cell.fen if cell.fen != "." else "empty"
        draw.text((px + 2, py + 4), f"{sq} · model {pred} {cell.confidence:.2f}",
                  font=fnt, fill=WHITE)
        alt = ", ".join(f"{c.fen} {c.conf:.2f}" for c in cell.alternatives[:3])
        draw.text((px + 2, py + 22), f"alternatives: {alt or 'none'}",
                  font=font(12), fill=(210, 210, 210))
        flags = ", ".join(cell.flags) or "flagged by validator"
        draw.text((px + 2, py + header + tile + 4), f"flags: {flags}",
                  font=font(12), fill=(255, 190, 90))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
