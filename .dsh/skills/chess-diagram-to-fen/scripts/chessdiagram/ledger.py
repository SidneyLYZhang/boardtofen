"""Manual fallback commands: ledger validation, FEN assembly, diff, render, grid."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from .constants import DARK, INK, LIGHT, PAPER, PIECE_GLYPHS
from .imaging import font, load_rgb, square_index, square_name
from .rules import (
    ascii_board, counts_line, fen_from_grid, grid_counts, parse_fen,
    parse_ledger, validate_grid,
)


def _structural_issues(grid) -> list[str]:
    counts = grid_counts(grid)
    issues: list[str] = []
    for side in ("white", "black"):
        if counts[side]["k"] != 1:
            issues.append(f"{side}: {counts[side]['k']} kings (need exactly 1)")
        if counts[side]["total"] > 16:
            issues.append(f"{side}: {counts[side]['total']} pieces (max 16)")
        if counts[side]["p"] > 8:
            issues.append(f"{side}: {counts[side]['p']} pawns (max 8)")
        pawns = counts[side]["p"]
        nonpawns = sum(counts[side][p] for p in "qrbn")
        if nonpawns > 7 + (8 - pawns):
            issues.append(f"{side}: {nonpawns} non-pawns with {pawns} pawns")
    for r in range(8):
        for c in range(8):
            if grid[r][c] in "Pp" and r in (0, 7):
                issues.append(f"pawn on {square_name(r, c)} (rank {8 - r}) cannot be a pawn")
    wk = [square_index(s) for s in
          (square_name(r, c) for r in range(8) for c in range(8) if grid[r][c] == "K")]
    bk = [square_index(s) for s in
          (square_name(r, c) for r in range(8) for c in range(8) if grid[r][c] == "k")]
    if len(wk) == 1 and len(bk) == 1:
        if abs(wk[0][0] - bk[0][0]) <= 1 and abs(wk[0][1] - bk[0][1]) <= 1:
            issues.append("kings are adjacent")
    return issues


def cmd_grid(args: argparse.Namespace) -> int:
    im = load_rgb(args.image)
    w, h = im.size
    step = max(25, args.step)
    canvas = im.copy()
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
    out = Path(args.out) if args.out else Path(args.image).with_name(
        Path(args.image).stem + "_grid.png")
    canvas.save(out)
    print(f"wrote {out} ({w}x{h}); step={step}px")
    return 0


def cmd_write_ledger(args: argparse.Namespace) -> int:
    raw = args.rows.replace("\r", "").replace("\n", ",")
    rows = [r.strip() for r in raw.split(",") if r.strip()]
    if len(rows) != 8:
        print(f"LEDGER ERROR: need 8 comma-separated rows, found {len(rows)}",
              file=sys.stderr)
        return 1
    _, errors = parse_ledger("\n".join(rows))
    if errors:
        for error in errors:
            print(f"LEDGER ERROR: {error}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {out} - 8x8 ledger, format valid")
    return 0


def cmd_counts(args: argparse.Namespace) -> int:
    grid, errors = parse_ledger(Path(args.ledger).read_text(encoding="utf-8"))
    if errors:
        for error in errors:
            print(f"LEDGER ERROR: {error}", file=sys.stderr)
        return 1
    assert grid is not None
    print(ascii_board(grid))
    print(counts_line(grid_counts(grid)))
    issues = _structural_issues(grid)
    if issues:
        print(f"LEDGER: FAIL ({len(issues)} structural issue(s))")
        for issue in issues:
            print(f"  ERROR: {issue}")
        return 1
    print("LEDGER: structurally OK (one king per side, pawn ranks and counts sane)")
    return 0


def _load_candidate(text_or_path: str):
    text = text_or_path
    try:
        path = Path(text_or_path)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
    except OSError:
        pass
    fields = text.split()
    if len(fields) == 6 and fields[0].count("/") == 7:
        parsed, errors = parse_fen(text)
        return (parsed["grid"] if parsed else None), errors
    if len([ln for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]) == 8:
        return parse_ledger(text)
    return parse_fen(text)


def cmd_compare(args: argparse.Namespace) -> int:
    a, ea = _load_candidate(args.a)
    b, eb = _load_candidate(args.b)
    if ea or eb:
        for error in ea + eb:
            print(f"PARSE ERROR: {error}", file=sys.stderr)
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
    for square, va, vb in diffs:
        print(f"  {square:6} {va:>8} {vb:>8}")
    return 1


def cmd_fen(args: argparse.Namespace) -> int:
    grid, errors = parse_ledger(Path(args.ledger).read_text(encoding="utf-8"))
    if errors:
        for error in errors:
            print(f"LEDGER ERROR: {error}", file=sys.stderr)
        return 1
    assert grid is not None
    fen = fen_from_grid(grid, args.turn, args.castling, args.ep,
                        args.halfmove, args.fullmove)
    print(fen)
    validation = validate_grid(grid, args.turn, args.castling, args.ep)
    if validation.errors:
        print(f"ARBITER: {len(validation.errors)} error(s) - run `check` for details",
              file=sys.stderr)
        return 1
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    parsed, errors = parse_fen(args.fen)
    if not parsed:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    grid = parsed["grid"]
    cell, margin = 100, 60
    w = h = margin * 2 + 8 * cell
    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)
    ox = oy = margin
    for r in range(8):
        for c in range(8):
            colour = LIGHT if (r + c) % 2 == 0 else DARK
            draw.rectangle([ox + c * cell, oy + r * cell,
                            ox + (c + 1) * cell, oy + (r + 1) * cell], fill=colour)
    sym_font = font(int(cell * 0.80), symbol=True)
    letter_font = font(int(cell * 0.62))
    use_glyph = bool(sym_font.getmask(PIECE_GLYPHS["k"]).getbbox())
    for r in range(8):
        for c in range(8):
            piece = grid[r][c]
            if piece == ".":
                continue
            x, y = ox + c * cell, oy + r * cell
            if use_glyph:
                glyph = PIECE_GLYPHS[piece.lower()]
                fill = (250, 248, 240) if piece.isupper() else (25, 25, 25)
                stroke = (25, 25, 25) if piece.isupper() else (250, 248, 240)
                bbox = draw.textbbox((0, 0), glyph, font=sym_font, stroke_width=2)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((x + (cell - tw) / 2 - bbox[0], y + (cell - th) / 2 - bbox[1]),
                          glyph, font=sym_font, fill=fill, stroke_width=2,
                          stroke_fill=stroke)
            else:
                label = piece.upper() if piece.isupper() else piece.lower()
                fill = (250, 248, 240) if piece.isupper() else (20, 20, 20)
                stroke = (20, 20, 20) if piece.isupper() else (250, 248, 240)
                bbox = draw.textbbox((0, 0), label, font=letter_font, stroke_width=2)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((x + (cell - tw) / 2 - bbox[0], y + (cell - th) / 2 - bbox[1]),
                          label, font=letter_font, fill=fill, stroke_width=2,
                          stroke_fill=stroke)
    for i in range(9):
        draw.line([(ox + i * cell, oy), (ox + i * cell, oy + 8 * cell)],
                  fill=(30, 30, 30), width=2)
        draw.line([(ox, oy + i * cell), (ox + 8 * cell, oy + i * cell)],
                  fill=(30, 30, 30), width=2)
    lf = font(22)
    for i in range(8):
        draw.text((ox + (i + 0.5) * cell, oy + 8 * cell + 12),
                  chr(ord("a") + i), font=lf, fill=INK, anchor="ma")
        draw.text((ox + (i + 0.5) * cell, oy - 12),
                  chr(ord("a") + i), font=lf, fill=INK, anchor="mb")
        draw.text((ox - 12, oy + (i + 0.5) * cell),
                  str(8 - i), font=lf, fill=INK, anchor="rm")
        draw.text((ox + 8 * cell + 12, oy + (i + 0.5) * cell),
                  str(8 - i), font=lf, fill=INK, anchor="lm")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out} - compare with board.png square by square")
    return 0
