#!/usr/bin/env python3
"""boardtool.py - stage a printed chess diagram, assemble its FEN, and check it.

Commands:
  prepare   detect the 8x8 grid, write labeled reading views
  grid      overlay a pixel grid for manual board-box selection
  inspect   zoom disputed squares into one labeled sheet
  counts    piece inventory of an 8x8 ledger
  compare   square-by-square diff of two ledgers (or FENs)
  write-ledger  write an 8x8 ledger, validating its format
  fen       assemble a FEN from an 8x8 ledger
  check     structural + legality check, ASCII board
  annotate  stamp the FEN onto the source board for final audit
  render    draw a FEN back as a labeled board image

Ledger format: 8 lines, rank 8 first, 8 characters per line,
FEN letters (uppercase = White, lowercase = Black), '.' = empty.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ---------------------------------------------------------------- constants

LIGHT = (241, 218, 181)
DARK = (181, 136, 99)
GRID_RED = (225, 40, 40)
LABEL = (180, 25, 35)
INK = (32, 32, 32)
PAPER = (252, 250, 244)
PIECES = set("pnbrqkPNBRQK")
GLYPHS = {"k": "\u265A", "q": "\u265B", "r": "\u265C", "b": "\u265D", "n": "\u265E", "p": "\u265F"}
FONT_PATHS = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "DejaVuSans.ttf",
]
SYMBOL_FONT_PATHS = [r"C:\Windows\Fonts\seguisym.ttf"] + FONT_PATHS


def font(size: int, symbol: bool = False) -> ImageFont.FreeTypeFont:
    for path in SYMBOL_FONT_PATHS if symbol else FONT_PATHS:
        try:
            f = ImageFont.truetype(path, size)
            if symbol:
                if not f.getmask(GLYPHS["k"]).getbbox():
                    continue
            return f
        except (OSError, ValueError):
            continue
    return ImageFont.load_default(size=size)


def load_rgb(path: str | Path) -> Image.Image:
    im = ImageOps.exif_transpose(Image.open(path))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, PAPER + (255,))
        im = Image.alpha_composite(bg, im)
    return im.convert("RGB")


def save_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- detection

def _smooth(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values.astype(np.float32)
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def _projection_scores(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = gray.astype(np.float32)
    gx = np.abs(np.diff(a, axis=1))
    gy = np.abs(np.diff(a, axis=0))
    col = np.zeros(a.shape[1], dtype=np.float32)
    row = np.zeros(a.shape[0], dtype=np.float32)
    col[: gx.shape[1]] = gx.sum(axis=0)
    row[: gy.shape[0]] = gy.sum(axis=1)
    col = _smooth(col, max(1, a.shape[1] // 350))
    row = _smooth(row, max(1, a.shape[0] // 350))
    return col, row


def _peaks(score: np.ndarray, min_dist: int, rel: float = 0.12, max_n: int = 70) -> np.ndarray:
    s = score.astype(np.float32)
    if len(s) < 3:
        return np.array([], dtype=int)
    local = np.where((s[1:-1] >= s[:-2]) & (s[1:-1] > s[2:]))[0] + 1
    if len(local) == 0:
        return np.array([], dtype=int)
    local = local[s[local] >= s.max() * rel]
    order = local[np.argsort(s[local])[::-1]]
    kept: list[int] = []
    for i in order:
        if all(abs(int(i) - j) >= min_dist for j in kept):
            kept.append(int(i))
        if len(kept) >= max_n:
            break
    return np.array(sorted(kept), dtype=int)


def _find_grid(score: np.ndarray, min_dim: float) -> tuple[float, float, float, list[int]] | None:
    """Find nine equally spaced grid lines by comb search over detected edge peaks."""
    peaks = _peaks(score, max(3, int(0.03 * min_dim)), rel=0.10, max_n=100)
    if len(peaks) < 3:
        return None
    span_lo, span_hi = 0.30 * min_dim, 0.99 * min_dim
    candidates: set[float] = set()
    for i in range(len(peaks)):
        for j in range(i + 1, len(peaks)):
            d = int(peaks[j] - peaks[i])
            for k in range(1, 9):
                s = d / k
                if span_lo / 8 <= s <= span_hi / 8:
                    candidates.add(round(s, 2))
    if not candidates:
        return None
    top = float(score.max())
    best: tuple[float, float, int, int] | None = None
    for s in candidates:
        if 8 * s < span_lo or 8 * s > span_hi:
            continue
        for start in peaks:
            if start + 8 * s >= len(score):
                continue
            total = 0.0
            hits = 0
            for k in range(9):
                p = start + k * s
                lo = max(0, int(p - 0.10 * s))
                hi = min(len(score), int(p + 0.10 * s) + 1)
                v = float(score[lo:hi].max())
                total += v
                if v >= 0.45 * top:
                    hits += 1
            if hits < 7:
                continue
            val = total * (hits / 9.0) ** 2
            if best is None or val > best[0]:
                best = (val, s, int(start), hits)
    if best is None:
        return None
    _, s, start, _ = best
    refined = []
    for k in range(9):
        expect = start + k * s
        lo = max(0, int(expect - 0.16 * s))
        hi = min(len(score), int(expect + 0.18 * s) + 1)
        if hi <= lo:
            return None
        refined.append(lo + int(np.argmax(score[lo:hi])))
    a, b = np.polyfit(np.arange(9), np.asarray(refined, dtype=np.float64), 1)
    residual = float(np.max(np.abs(np.asarray(refined) - (a * np.arange(9) + b))))
    if a <= 2 or residual > 0.08 * a:
        return None
    return float(a), float(b), residual, refined


def _downscale_for_detect(im: Image.Image, limit: int = 1300) -> tuple[Image.Image, float]:
    w, h = im.size
    scale = min(1.0, limit / max(w, h))
    if scale >= 1.0:
        return im, 1.0
    return im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS), scale


def estimate_skew(im: Image.Image) -> float:
    """Return a small rotation (degrees, PIL convention) that best aligns the grid."""
    gray = np.asarray(im.convert("L"), dtype=np.uint8)
    h, w = gray.shape
    scale = min(1.0, 900.0 / max(w, h))
    if scale < 1.0:
        gray = np.asarray(Image.fromarray(gray).resize(
            (max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR))
    base = Image.fromarray(gray)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-4.0, 4.01, 0.5):
        rotated = np.asarray(base.rotate(float(angle), resample=Image.Resampling.BILINEAR,
                                         expand=False, fillcolor=255), dtype=np.float32)
        col = np.abs(np.diff(rotated, axis=1)).sum(axis=0)
        row = np.abs(np.diff(rotated, axis=0)).sum(axis=1)
        score = float(np.sort(col)[-15:].mean() + np.sort(row)[-15:].mean())
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def detect_board(im: Image.Image) -> dict | None:
    small, scale = _downscale_for_detect(im)
    gray = np.asarray(small.convert("L"), dtype=np.uint8)
    col, row = _projection_scores(gray)
    h, w = gray.shape
    min_dim = min(w, h)
    fx = _find_grid(col, min_dim)
    fy = _find_grid(row, min_dim)
    if not fx or not fy:
        return None
    ax, bx, rx, _ = fx
    ay, by, ry, _ = fy
    if not (0.12 * min_dim <= 8 * ax <= 1.02 * min_dim):
        return None
    if not (0.12 * min_dim <= 8 * ay <= 1.02 * min_dim):
        return None
    if abs(ax - ay) / max(ax, ay) > 0.09:
        return None
    x0, x1 = bx, bx + 8 * ax
    y0, y1 = by, by + 8 * ay
    if x0 < -2 or y0 < -2 or x1 > w + 2 or y1 > h + 2:
        return None
    inv = 1.0 / scale
    return {
        "bbox": [x0 * inv, y0 * inv, x1 * inv, y1 * inv],
        "lines_x": [(bx + k * ax) * inv for k in range(9)],
        "lines_y": [(by + k * ay) * inv for k in range(9)],
        "square_px": ax * inv,
        "square_py": ay * inv,
        "residual": max(rx, ry) * inv,
        "detected_size": small.size,
    }


# ---------------------------------------------------------------- drawing helpers

def _draw_labeled_board(board: Image.Image, labels: list[str], labels_v: list[str],
                        title: str, out: Path, border: int = 2,
                        mark_grid: bool = True) -> None:
    """board: square board image; labels: file letters; labels_v: rank numbers."""
    cell = board.width / len(labels)
    margin_l = 48
    margin_r = 30
    margin_t = 62 if title else 40
    margin_b = 40
    w = board.width + margin_l + margin_r
    h = board.height + margin_t + margin_b
    canvas = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(canvas)
    lf = font(22)
    if title:
        draw.text((w / 2, 8), title, font=font(20), fill=(80, 80, 80), anchor="ma")
    ox, oy = margin_l, margin_t
    canvas.paste(board, (ox, oy))
    # labels
    for i, ch in enumerate(labels):
        cx = ox + (i + 0.5) * cell
        draw.text((cx, oy - 10), ch, font=lf, fill=LABEL, anchor="mb")
        draw.text((cx, oy + board.height + 10), ch, font=lf, fill=LABEL, anchor="ma")
    for i, ch in enumerate(labels_v):
        cy = oy + (i + 0.5) * (board.height / len(labels_v))
        draw.text((ox - 10, cy), ch, font=lf, fill=LABEL, anchor="rm")
        draw.text((ox + board.width + 10, cy), ch, font=lf, fill=LABEL, anchor="lm")
    # red square boundaries
    if mark_grid:
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for i in range(len(labels) + 1):
            x = ox + i * (board.width / len(labels))
            od.line([(x, oy), (x, oy + board.height)], fill=GRID_RED + (105,), width=1)
        for i in range(len(labels_v) + 1):
            y = oy + i * (board.height / len(labels_v))
            od.line([(ox, y), (ox + board.width, y)], fill=GRID_RED + (105,), width=1)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(canvas)
    draw.rectangle([ox, oy, ox + board.width, oy + board.height], outline=GRID_RED, width=border)
    canvas.save(out)


def _board_crop(im: Image.Image, bbox: list[float], flip: bool, size: int) -> Image.Image:
    crop = im.crop(tuple(int(round(v)) for v in bbox))
    if flip:
        crop = crop.transpose(Image.Transpose.ROTATE_180)
    return crop.resize((size, size), Image.Resampling.LANCZOS)


def parse_ledger(text: str) -> tuple[list[list[str]] | None, list[str]]:
    errors = []
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(line)
    if len(rows) != 8:
        errors.append(f"ledger needs exactly 8 non-comment lines, found {len(rows)}")
        return None, errors
    grid = []
    for i, row in enumerate(rows):
        if len(row) != 8:
            errors.append(f"rank line {i + 1} has {len(row)} characters, need 8: {row!r}")
            continue
        bad = sorted({ch for ch in row if ch not in PIECES and ch != "."})
        if bad:
            errors.append(f"rank line {i + 1} has invalid characters: {''.join(bad)!r}")
        grid.append(list(row))
    if len(grid) != 8:
        return None, errors
    return grid, errors


def ledger_to_fen(grid: list[list[str]]) -> str:
    parts = []
    for row in grid:
        out = []
        empty = 0
        for ch in row:
            if ch == ".":
                empty += 1
            else:
                if empty:
                    out.append(str(empty))
                    empty = 0
                out.append(ch)
        if empty:
            out.append(str(empty))
        parts.append("".join(out))
    return "/".join(parts)


def parse_fen(fen: str) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    fields = fen.strip().split()
    if len(fields) != 6:
        return None, [f"FEN needs 6 space-separated fields, found {len(fields)}"]
    board_part, turn, castling, ep, half, full = fields
    if turn not in ("w", "b"):
        errors.append(f"active color must be w or b, found {turn!r}")
    rows = board_part.split("/")
    if len(rows) != 8:
        errors.append(f"board field needs 8 ranks, found {len(rows)}")
        return None, errors
    grid: list[list[str]] = []
    for r, row in enumerate(rows):
        cells: list[str] = []
        prev_digit = False
        for ch in row:
            if ch.isdigit():
                if ch == "0":
                    errors.append(f"rank {8 - r}: digit 0 is not valid")
                    prev_digit = True
                    continue
                if prev_digit:
                    errors.append(f"rank {8 - r}: adjacent digits {row!r} are not a valid empty run")
                cells.extend(["."] * int(ch))
                prev_digit = True
            elif ch in PIECES:
                cells.append(ch)
                prev_digit = False
            else:
                errors.append(f"rank {8 - r}: invalid character {ch!r}")
                prev_digit = False
        if len(cells) != 8:
            errors.append(f"rank {8 - r} expands to {len(cells)} squares, need 8")
            continue
        grid.append(cells)
    if len(grid) != 8:
        return None, errors
    if not re.fullmatch(r"\d+", half):
        errors.append(f"halfmove clock must be a non-negative integer, found {half!r}")
    if not re.fullmatch(r"\d+", full):
        errors.append(f"fullmove number must be a positive integer, found {full!r}")
    elif int(full) < 1:
        errors.append(f"fullmove number must be at least 1, found {full!r}")
    meta = {"turn": turn, "castling": castling, "ep": ep, "halfmove": half, "fullmove": full}
    return {"grid": grid, "meta": meta, "fen": " ".join(fields)}, errors


def fen_from_grid(grid: list[list[str]], turn: str = "w", castling: str = "-",
                  ep: str = "-", halfmove: int = 0, fullmove: int = 1) -> str:
    return f"{ledger_to_fen(grid)} {turn} {castling or '-'} {ep or '-'} {halfmove} {fullmove}"


def grid_counts(grid: list[list[str]]) -> dict:
    counts = {}
    for side in ("white", "black"):
        counts[side] = {k: 0 for k in "kqrbnp"}
    for row in grid:
        for ch in row:
            if ch == ".":
                continue
            side = "white" if ch.isupper() else "black"
            counts[side][ch.lower()] += 1
    for side in counts:
        counts[side]["total"] = sum(counts[side].values())
    return counts


def square_name(rank_i: int, file_i: int) -> str:
    return f"{chr(ord('a') + file_i)}{8 - rank_i}"


def square_index(name: str) -> tuple[int, int]:
    if not re.fullmatch(r"[a-h][1-8]", name.strip().lower()):
        raise ValueError(f"bad square {name!r}")
    name = name.strip().lower()
    return 8 - int(name[1]), ord(name[0]) - ord("a")


def attacked(grid: list[list[str]], rank_i: int, file_i: int, by_white: bool) -> bool:
    """Is the square attacked by the given side?"""
    # pawns
    if by_white:
        for df in (-1, 1):
            r, c = rank_i + 1, file_i + df
            if 0 <= r < 8 and 0 <= c < 8 and grid[r][c] == "P":
                return True
    else:
        for df in (-1, 1):
            r, c = rank_i - 1, file_i + df
            if 0 <= r < 8 and 0 <= c < 8 and grid[r][c] == "p":
                return True
    # knights
    for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)):
        r, c = rank_i + dr, file_i + dc
        if 0 <= r < 8 and 0 <= c < 8:
            p = grid[r][c]
            if (by_white and p == "N") or ((not by_white) and p == "n"):
                return True
    # king
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = rank_i + dr, file_i + dc
            if 0 <= r < 8 and 0 <= c < 8:
                p = grid[r][c]
                if (by_white and p == "K") or ((not by_white) and p == "k"):
                    return True
    # sliders
    for dr, dc, kinds in ((-1, 0, "RQ"), (1, 0, "RQ"), (0, -1, "RQ"), (0, 1, "RQ"),
                          (-1, -1, "BQ"), (-1, 1, "BQ"), (1, -1, "BQ"), (1, 1, "BQ")):
        r, c = rank_i + dr, file_i + dc
        while 0 <= r < 8 and 0 <= c < 8:
            p = grid[r][c]
            if p != ".":
                if p.isupper() == by_white and p.upper() in kinds:
                    return True
                break
            r += dr
            c += dc
    return False


def find_king(grid: list[list[str]], white: bool) -> tuple[int, int] | None:
    target = "K" if white else "k"
    found = [(r, c) for r in range(8) for c in range(8) if grid[r][c] == target]
    return found[0] if len(found) == 1 else None


def basic_issues(grid: list[list[str]]) -> tuple[list[str], dict]:
    """Structural problems visible without turn/history metadata."""
    errors: list[str] = []
    counts = grid_counts(grid)
    kings = {"white": counts["white"]["k"], "black": counts["black"]["k"]}
    for side, n in kings.items():
        if n != 1:
            errors.append(f"{side}: {n} kings (need exactly 1)")
    for r in range(8):
        for c in range(8):
            p = grid[r][c]
            if p in "Pp" and r in (0, 7):
                errors.append(f"pawn on {square_name(r, c)} (rank {8 - r}) cannot be a pawn")
    for side in ("white", "black"):
        if counts[side]["total"] > 16:
            errors.append(f"{side}: {counts[side]['total']} pieces (max 16)")
        if counts[side]["p"] > 8:
            errors.append(f"{side}: {counts[side]['p']} pawns (max 8)")
    wk, bk = find_king(grid, True), find_king(grid, False)
    if wk and bk and abs(wk[0] - bk[0]) <= 1 and abs(wk[1] - bk[1]) <= 1:
        errors.append("kings are adjacent")
    return errors, counts


def check_position(grid: list[list[str]], meta: dict) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors, counts = basic_issues(grid)
    if meta["turn"] not in ("w", "b"):
        errors.append(f"active color {meta['turn']!r} is not w/b")
    wk, bk = find_king(grid, True), find_king(grid, False)
    if wk and bk:
        adjacent = abs(wk[0] - bk[0]) <= 1 and abs(wk[1] - bk[1]) <= 1
        if not adjacent:
            white_in_check = attacked(grid, wk[0], wk[1], False)
            black_in_check = attacked(grid, bk[0], bk[1], True)
            if white_in_check and black_in_check:
                errors.append("both kings are in check")
            elif meta["turn"] == "w" and black_in_check:
                errors.append("Black is in check but it is White's turn (illegal)")
            elif meta["turn"] == "b" and white_in_check:
                errors.append("White is in check but it is Black's turn (illegal)")
    # castling
    rights = meta["castling"]
    if rights != "-":
        if not re.fullmatch(r"[KQkq]+", rights) or len(set(rights)) != len(rights):
            errors.append(f"castling field {rights!r} must be '-' or unique letters KQkq")
        else:
            need = {
                "K": ("e1", "h1", "K", "R"),
                "Q": ("e1", "a1", "K", "R"),
                "k": ("e8", "h8", "k", "r"),
                "q": ("e8", "a8", "k", "r"),
            }
            for ch in rights:
                ksq, rsq, kp, rp = need[ch]
                if grid[square_index(ksq)[0]][square_index(ksq)[1]] != kp or \
                   grid[square_index(rsq)[0]][square_index(rsq)[1]] != rp:
                    errors.append(f"castling right {ch!r} requires {kp} on {ksq} and {rp} on {rsq}")
    # en passant
    ep = meta["ep"]
    if ep != "-":
        try:
            er, ec = square_index(ep)
        except ValueError:
            errors.append(f"en passant target {ep!r} is not a square")
        else:
            if meta["turn"] == "w":
                if er != 2:
                    errors.append(f"en passant target {ep} must be on rank 6 when White moves")
                pawn_r, pawn = er + 1, "p"
            else:
                if er != 5:
                    errors.append(f"en passant target {ep} must be on rank 3 when Black moves")
                pawn_r, pawn = er - 1, "P"
            if not (0 <= pawn_r < 8) or grid[pawn_r][ec] != pawn:
                errors.append(f"en passant {ep}: no {pawn!r} on {square_name(pawn_r, ec)}")
            if grid[er][ec] != ".":
                errors.append(f"en passant target square {ep} is occupied")
    return errors, warnings


def ascii_board(grid: list[list[str]]) -> str:
    letters = {"K": "K", "Q": "Q", "R": "R", "B": "B", "N": "N", "P": "P",
               "k": "k", "q": "q", "r": "r", "b": "b", "n": "n", "p": "p", ".": "."}
    lines = ["    a b c d e f g h"]
    for r in range(8):
        cells = " ".join(letters[ch] for ch in grid[r])
        lines.append(f"  {8 - r} {cells}  {8 - r}")
    lines.append("    a b c d e f g h")
    return "\n".join(lines)


def counts_line(counts: dict) -> str:
    order = "kqrbnp"
    parts = []
    for side in ("white", "black"):
        c = counts[side]
        detail = " ".join(f"{k.upper() if side == 'white' else k}{c[k]}" for k in order)
        parts.append(f"{side.capitalize()}: {detail} = {c['total']}")
    return " | ".join(parts)


# ---------------------------------------------------------------- commands

def cmd_grid(args: argparse.Namespace) -> int:
    im = load_rgb(args.image)
    w, h = im.size
    step = max(25, args.step)
    canvas = im.copy()
    draw = ImageDraw.Draw(canvas)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, w, step):
        od.line([(x, 0), (x, h)], fill=(60, 120, 220, 90), width=1)
    for y in range(0, h, step):
        od.line([(0, y), (w, y)], fill=(60, 120, 220, 90), width=1)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    lf = font(max(14, min(w, h) // 70))
    for x in range(0, w, step * 2):
        for y in range(0, h, step * 2):
            draw.text((x + 3, y + 2), f"{x},{y}", font=lf, fill=(20, 60, 150))
    out = Path(args.out) if args.out else Path(args.image).with_name(Path(args.image).stem + "_grid.png")
    canvas.save(out)
    print(f"wrote {out} ({w}x{h}); step={step}px")
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    src = load_rgb(args.image)
    work = Path(args.out)
    work.mkdir(parents=True, exist_ok=True)

    if args.bbox:
        try:
            x0, y0, x1, y1 = [float(v) for v in args.bbox.split(",")]
        except ValueError:
            print("error: --bbox must be x0,y0,x1,y1", file=sys.stderr)
            return 2
        if not (0 <= x0 < x1 <= src.width and 0 <= y0 < y1 <= src.height):
            print(f"error: bbox outside image bounds {src.size}", file=sys.stderr)
            return 2
        working = src
        lines_x = [x0 + (x1 - x0) * k / 8 for k in range(9)]
        lines_y = [y0 + (y1 - y0) * k / 8 for k in range(9)]
        info = {"bbox": [x0, y0, x1, y1], "lines_x": lines_x, "lines_y": lines_y,
                "square_px": (x1 - x0) / 8, "square_py": (y1 - y0) / 8,
                "residual": 0, "manual_bbox": True, "skew": 0}
    else:
        skew = estimate_skew(src) if not args.no_deskew else 0.0
        if abs(skew) >= 0.25:
            working = src.rotate(skew, resample=Image.Resampling.BICUBIC, expand=True,
                                 fillcolor=PAPER)
        else:
            skew = 0.0
            working = src
        found = detect_board(working)
        if not found:
            grid_path = work / "grid.png"
            cmd_grid(argparse.Namespace(image=args.image, out=str(grid_path), step=args.grid_step))
            print("error: could not lock onto an 8x8 grid.", file=sys.stderr)
            print(f"inspect {grid_path} and rerun with --bbox x0,y0,x1,y1", file=sys.stderr)
            return 3
        info = found
        info["manual_bbox"] = False
        info["skew"] = skew

    info["image"] = str(Path(args.image).resolve())
    info["flip"] = bool(args.flip)
    info["working_image"] = str((work / "working.png").resolve())
    working.save(work / "working.png")

    # full-resolution normalized board
    board = _board_crop(working, info["bbox"], args.flip, 8 * 170)
    _draw_labeled_board(
        board,
        list("abcdefgh"),
        [str(r) for r in range(8, 0, -1)],
        "contact — normalized, White at bottom",
        work / "contact.png",
    )

    # quadrants: 4x4, deep zoom
    qcell = 220
    qboard = _board_crop(working, info["bbox"], args.flip, 8 * qcell)
    corners = [("q1", 0, 0, "Q1 · a8–d5"), ("q2", 4, 0, "Q2 · e8–h5"),
               ("q3", 0, 4, "Q3 · a4–d1"), ("q4", 4, 4, "Q4 · e4–h1")]
    for name, fx, fy, title in corners:
        tile = qboard.crop((fx * qcell, fy * qcell, (fx + 4) * qcell, (fy + 4) * qcell))
        files = list("abcdefgh")[fx:fx + 4]
        ranks = [str(r) for r in range(8 - fy, 8 - fy - 4, -1)]
        _draw_labeled_board(tile, files, ranks, title, work / f"{name}.png")

    # halves: 8x4, a different slicing for the blind second read
    hcell = 170
    hboard = _board_crop(working, info["bbox"], args.flip, 8 * hcell)
    _draw_labeled_board(hboard.crop((0, 0, 8 * hcell, 4 * hcell)),
                        list("abcdefgh"), ["8", "7", "6", "5"],
                        "half A · ranks 8–5", work / "half_top.png")
    _draw_labeled_board(hboard.crop((0, 4 * hcell, 8 * hcell, 8 * hcell)),
                        list("abcdefgh"), ["4", "3", "2", "1"],
                        "half B · ranks 4–1", work / "half_bottom.png")

    # overlay for geometry verification
    scale = min(1.0, 1500 / max(working.size))
    preview = working.resize((int(working.width * scale), int(working.height * scale)),
                             Image.Resampling.LANCZOS).convert("RGBA")
    od = ImageDraw.Draw(preview)
    for x in info["lines_x"]:
        od.line([(x * scale, info["lines_y"][0] * scale), (x * scale, info["lines_y"][8] * scale)],
                fill=GRID_RED + (210,), width=3)
    for y in info["lines_y"]:
        od.line([(info["lines_x"][0] * scale, y * scale), (info["lines_x"][8] * scale, y * scale)],
                fill=GRID_RED + (210,), width=3)
    preview.convert("RGB").save(work / "overlay.png")
    info["outputs"] = {name: str((work / name).resolve()) for name in
                       ["working.png", "overlay.png", "contact.png", "q1.png", "q2.png",
                        "q3.png", "q4.png", "half_top.png", "half_bottom.png"]}
    save_json(work / "board.json", info)
    print(json.dumps({
        "ok": True,
        "bbox": [round(v, 1) for v in info["bbox"]],
        "square_px": round(info["square_px"], 2),
        "skew": round(info.get("skew", 0), 2),
        "flip": info["flip"],
        "outputs": info["outputs"],
    }, indent=2))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.board).read_text(encoding="utf-8"))
    im = load_rgb(args.image or data.get("working_image"))
    squares = [s.strip().lower() for s in args.squares.split(",") if s.strip()]
    if not squares:
        print("error: --squares is empty", file=sys.stderr)
        return 2
    tile = 330
    label_h = 42
    per_row = min(4, len(squares))
    rows = math.ceil(len(squares) / per_row)
    pad = 12
    w = per_row * (tile + pad) + pad
    h = rows * (tile + label_h + pad) + pad
    sheet = Image.new("RGB", (w, h), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    lf = font(24)
    for i, sq in enumerate(squares):
        try:
            square_index(sq)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        file_i = ord(sq[0]) - ord("a")
        rank_i = 8 - int(sq[1])
        if data.get("flip", False):
            file_i, rank_i = 7 - file_i, 7 - rank_i
        x0, x1 = data["lines_x"][file_i], data["lines_x"][file_i + 1]
        y0, y1 = data["lines_y"][rank_i], data["lines_y"][rank_i + 1]
        side = min(x1 - x0, y1 - y0)
        pad_px = int(round(side * 0.22))
        left, top = max(0, int(x0 - pad_px)), max(0, int(y0 - pad_px))
        right = min(im.width, int(x1 + pad_px))
        bottom = min(im.height, int(y1 + pad_px))
        big = im.crop((left, top, right, bottom))
        sx, sy = tile / big.width, tile / big.height
        big = big.resize((tile, tile), Image.Resampling.LANCZOS)
        d2 = ImageDraw.Draw(big)
        rect = [(x0 - left) * sx, (y0 - top) * sy,
                (x1 - left) * sx, (y1 - top) * sy]
        d2.rectangle(rect, outline=GRID_RED, width=3)
        col = i % per_row
        row = i // per_row
        x = pad + col * (tile + pad)
        y = pad + row * (tile + label_h + pad)
        sheet.paste(big, (x, y + label_h))
        draw.text((x + tile / 2, y + 6), sq, font=lf, fill=(255, 255, 255), anchor="ma")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"wrote {out} - {len(squares)} square(s), target outlined in red")
    return 0


def cmd_counts(args: argparse.Namespace) -> int:
    grid, errors = parse_ledger(Path(args.ledger).read_text(encoding="utf-8"))
    if errors:
        for e in errors:
            print(f"LEDGER ERROR: {e}", file=sys.stderr)
        return 1
    assert grid is not None
    issues, counts = basic_issues(grid)
    print(ascii_board(grid))
    print(counts_line(counts))
    if issues:
        print(f"LEDGER: FAIL ({len(issues)} structural issue(s))")
        for e in issues:
            print(f"  ERROR: {e}")
        return 1
    print("LEDGER: structurally OK (one king per side, pawn ranks and counts sane)")
    return 0


def _load_candidate(text_or_path: str) -> tuple[list[list[str]] | None, list[str]]:
    text = text_or_path
    try:
        p = Path(text_or_path)
        if p.is_file():
            text = p.read_text(encoding="utf-8")
    except OSError:
        pass
    fields = text.split()
    if len(fields) == 6 and fields[0].count("/") == 7:
        parsed, errors = parse_fen(text)
        return (parsed["grid"] if parsed else None), errors
    if len([ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]) == 8:
        return parse_ledger(text)
    return parse_fen(text)


def cmd_compare(args: argparse.Namespace) -> int:
    a, ea = _load_candidate(args.a)
    b, eb = _load_candidate(args.b)
    if ea or eb:
        for e in ea + eb:
            print(f"PARSE ERROR: {e}", file=sys.stderr)
        return 2
    assert a is not None and b is not None
    diffs = []
    for r in range(8):
        for c in range(8):
            if a[r][c] != b[r][c]:
                diffs.append((square_name(r, c), a[r][c], b[r][c]))
    if not diffs:
        print("MATCH: all 64 squares agree")
        return 0
    print(f"{len(diffs)} square(s) differ:")
    print(f"  {'square':6} {'A':>8} {'B':>8}")
    for sq, va, vb in diffs:
        print(f"  {sq:6} {va:>8} {vb:>8}")
    return 1


def cmd_write_ledger(args: argparse.Namespace) -> int:
    raw = args.rows.replace("\r", "").replace("\n", ",")
    rows = [r.strip() for r in raw.split(",") if r.strip()]
    if len(rows) != 8:
        print(f"LEDGER ERROR: need 8 comma-separated rows, found {len(rows)}", file=sys.stderr)
        return 1
    _, errors = parse_ledger("\n".join(rows))
    if errors:
        for e in errors:
            print(f"LEDGER ERROR: {e}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {out} - 8x8 ledger, format valid")
    return 0


def cmd_fen(args: argparse.Namespace) -> int:
    grid, errors = parse_ledger(Path(args.ledger).read_text(encoding="utf-8"))
    if errors:
        for e in errors:
            print(f"LEDGER ERROR: {e}", file=sys.stderr)
        return 1
    assert grid is not None
    fen = fen_from_grid(grid, args.turn, args.castling, args.ep, args.halfmove, args.fullmove)
    print(fen)
    errs, warns = check_position(grid, {"turn": args.turn, "castling": args.castling,
                                        "ep": args.ep, "halfmove": str(args.halfmove),
                                        "fullmove": str(args.fullmove)})
    for w in warns:
        print(f"WARNING: {w}", file=sys.stderr)
    if errs:
        print(f"ARBITER: {len(errs)} error(s) - run `check` for the full report", file=sys.stderr)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    parsed, errors = parse_fen(args.fen)
    if not parsed:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print("ARBITER: FAIL (malformed FEN)")
        return 1
    grid, meta = parsed["grid"], parsed["meta"]
    errs, warns = check_position(grid, meta)
    errs = errors + errs
    print(f"FEN: {parsed['fen']}")
    print(ascii_board(grid))
    print(counts_line(grid_counts(grid)))
    print(f"turn={meta['turn']} castling={meta['castling']} ep={meta['ep']} "
          f"halfmove={meta['halfmove']} fullmove={meta['fullmove']}")
    # optional deeper cross-check with python-chess
    try:
        import chess  # type: ignore
        try:
            board = chess.Board(parsed["fen"])
            status = board.status()
            if board.is_valid():
                print("python-chess: valid")
            else:
                print(f"python-chess: invalid ({status!r})")
            if board.is_check():
                print(f"python-chess: side to move is in check")
        except ValueError as exc:
            print(f"python-chess: rejected ({exc})")
    except ImportError:
        pass
    if errs:
        print(f"ARBITER: FAIL ({len(errs)} error(s))")
        for e in errs:
            print(f"  ERROR: {e}")
    else:
        print("ARBITER: PASS")
    for w in warns:
        print(f"  WARNING: {w}")
    if args.json:
        print(json.dumps({"fen": parsed["fen"], "ok": not errs, "errors": errs, "warnings": warns}))
    return 1 if errs else 0


def cmd_annotate(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.board).read_text(encoding="utf-8"))
    parsed, errors = parse_fen(args.fen)
    if not parsed:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    grid = parsed["grid"]
    im = load_rgb(args.image or data.get("working_image"))
    cell = 170
    board = _board_crop(im, data["bbox"], data.get("flip", False), 8 * cell)
    draw = ImageDraw.Draw(board, "RGBA")
    lf = font(int(cell * 0.22))
    for r in range(8):
        for c in range(8):
            ch = grid[r][c]
            x, y = c * cell, r * cell
            pad = int(cell * 0.030)
            box = int(cell * 0.245)
            draw.rounded_rectangle([x + pad, y + pad, x + pad + box, y + pad + box],
                                   radius=4, fill=(255, 255, 255, 220))
            if ch == ".":
                color, text = (105, 105, 105, 255), "\u00b7"
            elif ch.isupper():
                color, text = (185, 20, 20, 255), ch
            else:
                color, text = (25, 60, 185, 255), ch
            draw.text((x + pad + box / 2, y + pad + box / 2), text, font=lf,
                      fill=color, anchor="mm")
    _draw_labeled_board(
        board, list("abcdefgh"), [str(r) for r in range(8, 0, -1)],
        "audit — red=White, blue=Black, dot=empty", Path(args.out))
    print(f"wrote {args.out} - check every square: label vs printed piece")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    parsed, errors = parse_fen(args.fen)
    if not parsed:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    grid = parsed["grid"]
    cell, margin = 100, 60
    w = margin * 2 + 8 * cell
    h = margin * 2 + 8 * cell
    img = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(img)
    ox, oy = margin, margin
    for r in range(8):
        for c in range(8):
            color = LIGHT if (r + c) % 2 == 0 else DARK
            d.rectangle([ox + c * cell, oy + r * cell, ox + (c + 1) * cell, oy + (r + 1) * cell],
                        fill=color)
    sym_font = font(int(cell * 0.80), symbol=True)
    letter_font = font(int(cell * 0.62))
    use_glyph = bool(sym_font.getmask(GLYPHS["k"]).getbbox())
    for r in range(8):
        for c in range(8):
            p = grid[r][c]
            if p == ".":
                continue
            x, y = ox + c * cell, oy + r * cell
            if use_glyph:
                glyph = GLYPHS[p.lower()]
                fill = (250, 248, 240) if p.isupper() else (25, 25, 25)
                stroke = (25, 25, 25) if p.isupper() else (250, 248, 240)
                sw = 2
                bbox = d.textbbox((0, 0), glyph, font=sym_font, stroke_width=sw)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                d.text((x + (cell - tw) / 2 - bbox[0], y + (cell - th) / 2 - bbox[1]),
                       glyph, font=sym_font, fill=fill, stroke_width=sw, stroke_fill=stroke)
            else:
                label = p.upper() if p.isupper() else p.lower()
                fill = (250, 248, 240) if p.isupper() else (20, 20, 20)
                stroke = (20, 20, 20) if p.isupper() else (250, 248, 240)
                bbox = d.textbbox((0, 0), label, font=letter_font, stroke_width=2)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                d.text((x + (cell - tw) / 2 - bbox[0], y + (cell - th) / 2 - bbox[1]),
                       label, font=letter_font, fill=fill, stroke_width=2, stroke_fill=stroke)
    for i in range(9):
        d.line([(ox + i * cell, oy), (ox + i * cell, oy + 8 * cell)], fill=(30, 30, 30), width=2)
        d.line([(ox, oy + i * cell), (ox + 8 * cell, oy + i * cell)], fill=(30, 30, 30), width=2)
    lf = font(22)
    for i in range(8):
        d.text((ox + (i + 0.5) * cell, oy + 8 * cell + 12), chr(ord("a") + i), font=lf, fill=INK, anchor="ma")
        d.text((ox + (i + 0.5) * cell, oy - 12), chr(ord("a") + i), font=lf, fill=INK, anchor="mb")
        d.text((ox - 12, oy + (i + 0.5) * cell), str(8 - i), font=lf, fill=INK, anchor="rm")
        d.text((ox + 8 * cell + 12, oy + (i + 0.5) * cell), str(8 - i), font=lf, fill=INK, anchor="lm")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out} - compare with contact.png square by square")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="detect the grid and write labeled reading views")
    p.add_argument("image")
    p.add_argument("--out", required=True)
    p.add_argument("--bbox", help="manual x0,y0,x1,y1 (skips detection and deskew)")
    p.add_argument("--flip", action="store_true", help="rotate the board 180° (Black at bottom)")
    p.add_argument("--no-deskew", action="store_true")
    p.add_argument("--grid-step", type=int, default=50)
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("grid", help="pixel-grid overlay for finding a manual bbox")
    p.add_argument("image")
    p.add_argument("--out")
    p.add_argument("--step", type=int, default=50)
    p.set_defaults(func=cmd_grid)

    p = sub.add_parser("inspect", help="zoom disputed squares into one sheet")
    p.add_argument("--board", required=True, help="board.json written by prepare")
    p.add_argument("--squares", required=True, help="comma-separated, e.g. e4,d5,f6")
    p.add_argument("--out", required=True)
    p.add_argument("--image", help="override image path (default: board.json working_image)")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("counts", help="piece inventory of a ledger")
    p.add_argument("ledger")
    p.set_defaults(func=cmd_counts)

    p = sub.add_parser("compare", help="square-by-square diff of two ledgers or FENs")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("write-ledger", help="write an 8x8 ledger, validating its format")
    p.add_argument("--out", required=True)
    p.add_argument("--rows", required=True,
                   help='8 rows separated by commas or newlines, rank 8 first')
    p.set_defaults(func=cmd_write_ledger)

    p = sub.add_parser("fen", help="assemble a FEN from a ledger")
    p.add_argument("--ledger", required=True)
    p.add_argument("--turn", choices=["w", "b"], default="w")
    p.add_argument("--castling", default="-")
    p.add_argument("--ep", default="-")
    p.add_argument("--halfmove", type=int, default=0)
    p.add_argument("--fullmove", type=int, default=1)
    p.set_defaults(func=cmd_fen)

    p = sub.add_parser("check", help="validate a FEN and print the board")
    p.add_argument("fen")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("annotate", help="stamp a FEN onto the source board for final audit")
    p.add_argument("--board", required=True, help="board.json written by prepare")
    p.add_argument("--fen", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--image", help="override image path")
    p.set_defaults(func=cmd_annotate)

    p = sub.add_parser("render", help="draw a FEN as a labeled board image")
    p.add_argument("fen")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_render)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
