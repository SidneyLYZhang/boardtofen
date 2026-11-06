#!/usr/bin/env python3
"""boardtool.py - model-backed chess diagram to FEN, plus manual ledger tools.

Primary workflow
  solve   detect every board, orient it, split 64 cells, run the 2d-chess-ocr
          model twice, assemble a FEN, validate it with chess rules, and write
          audit images.
  apply   apply visual corrections to flagged squares and rebuild the FEN.
  check   validate any FEN and print the board and square-level diagnosis.

Supporting commands
  stage, read, review, inspect, annotate, render, compare, grid,
  write-ledger, counts, fen.

FEN defaults: w - - 0 1.  Only the placement is read from the image; change
the other fields only when the page actually states them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from chessdiagram.constants import (  # noqa: E402
    DEFAULT_CASTLING, DEFAULT_EP, DEFAULT_FULLMOVE, DEFAULT_HALFMOVE,
    DEFAULT_TURN,
)
from chessdiagram.imaging import load_rgb  # noqa: E402
from chessdiagram.ledger import (  # noqa: E402
    cmd_compare, cmd_counts, cmd_fen, cmd_grid, cmd_render, cmd_write_ledger,
)
from chessdiagram.pipeline import (  # noqa: E402
    SolveOptions, apply_changes, load_report, review_sheet, solve,
)
from chessdiagram.rules import (  # noqa: E402
    ascii_board, counts_line, grid_counts, parse_fen, validate_fen,
)


def _print_error(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _add_model_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", help="path to a .onnx detector (overrides the model store)")
    p.add_argument("--variant", choices=["auto", "m", "n"], default="auto",
                   help="model size: m = accurate (default), n = small")
    p.add_argument("--model-dir", help="directory containing the ONNX weights")
    p.add_argument("--download", action="store_true",
                   help="download the model if it is missing (no implicit network)")
    p.add_argument("--mirror", help="Hugging Face mirror, e.g. https://hf-mirror.com")


def _solve_options(args: argparse.Namespace) -> SolveOptions:
    bbox = None
    if getattr(args, "bbox", None):
        try:
            values = [float(v) for v in args.bbox.split(",")]
            if len(values) != 4:
                raise ValueError
            bbox = tuple(values)
        except ValueError:
            raise SystemExit("--bbox must be x0,y0,x1,y1")
    explicit_meta = (
        args.turn != DEFAULT_TURN
        or args.castling != DEFAULT_CASTLING
        or args.ep != DEFAULT_EP
        or args.halfmove != DEFAULT_HALFMOVE
        or args.fullmove != DEFAULT_FULLMOVE)
    return SolveOptions(
        image=getattr(args, "image", ""), out=args.out,
        board_index=getattr(args, "board_index", None), bbox=bbox,
        orientation=args.orientation, flip=args.flip, model=args.model,
        variant=args.variant, model_dir=args.model_dir,
        allow_download=args.download, mirror=args.mirror,
        conf=args.conf, review_conf=args.review_conf, deskew=not args.no_deskew,
        threads=args.threads, turn=args.turn, castling=args.castling,
        ep=args.ep, halfmove=args.halfmove, fullmove=args.fullmove,
        metadata_source="user" if explicit_meta else "default",
        strict=args.strict)


def cmd_solve(args: argparse.Namespace) -> int:
    opts = _solve_options(args)
    report = solve(opts)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(report.get("summary", ""))
        if report.get("ok") and report.get("artifacts"):
            print("FILES " + " ".join(
                str(report["artifacts"].get(k))
                for k in ("audit", "review", "cells_sheet", "cells", "cells_json",
                          "report")
                if report["artifacts"].get(k)))
    code = int(report.get("exit_code", 0))
    if code == 0 and args.strict and report.get("ok"):
        if not report.get("validation", {}).get("legal", True):
            code = 1
    return code


def cmd_stage(args: argparse.Namespace) -> int:
    """Detect the board and write cells; no OCR, no FEN."""
    from chessdiagram.pipeline import stage
    opts = _solve_options(args)
    report = stage(opts)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json
          else report.get("summary", ""))
    return int(report.get("exit_code", 0))


def cmd_read(args: argparse.Namespace) -> int:
    from chessdiagram.pipeline import read_board
    opts = _solve_options(args)
    report = read_board(args.board, opts)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(report.get("summary", ""))
    return int(report.get("exit_code", 0))


def cmd_apply(args: argparse.Namespace) -> int:
    changes: dict[str, str] = {}
    for item in args.set.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            return _print_error(f"--set item {item!r} must look like e4=Q or e4=.")
        square, value = item.split("=", 1)
        changes[square.strip()] = value.strip()
    if not changes:
        return _print_error("--set is empty")
    try:
        report = apply_changes(args.board, changes, args.note or "")
    except Exception as exc:
        return _print_error(f"apply failed: {exc}")
    print(report.get("summary", ""))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    squares = [s.strip() for s in args.squares.split(",") if s.strip()] \
        if args.squares else None
    try:
        result = review_sheet(args.board, squares, args.out)
    except Exception as exc:
        return _print_error(f"review failed: {exc}")
    if not result["ok"]:
        print("no review squares; nothing to draw")
        return 0
    print(f"wrote {result['review']} - {len(result['squares'])} square(s)")
    for sq in result["squares"]:
        print(f"  {sq}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    validation = validate_fen(args.fen)
    parsed, syntax = parse_fen(args.fen)
    if parsed is None:
        for msg in syntax:
            print(f"ERROR: {msg}", file=sys.stderr)
        print("ARBITER: FAIL (malformed FEN)")
        if args.json:
            print(json.dumps({"fen": args.fen, "ok": False,
                              "errors": syntax}, indent=2))
        return 1
    grid, meta = parsed["grid"], parsed["meta"]
    print(f"FEN: {parsed['fen']}")
    print(ascii_board(grid))
    print(counts_line(grid_counts(grid)))
    print(f"turn={meta['turn']} castling={meta['castling']} ep={meta['ep']} "
          f"halfmove={meta['halfmove']} fullmove={meta['fullmove']}")
    print(f"python-chess: {validation.python_chess}")
    if validation.warnings:
        for warning in validation.warnings:
            print(f"  WARNING: {warning}")
    if validation.errors:
        print(f"ARBITER: FAIL ({len(validation.errors)} error(s))")
        for issue in validation.errors:
            squares = f" [{', '.join(issue.squares)}]" if issue.squares else ""
            print(f"  ERROR: {issue.message}{squares}")
    else:
        print("ARBITER: PASS")
    if args.json:
        print(json.dumps({
            "fen": parsed["fen"], "ok": validation.legal,
            "validation": validation.to_dict(),
        }, indent=2, ensure_ascii=False))
    return 0 if validation.legal else 1


def cmd_annotate(args: argparse.Namespace) -> int:
    """Stamp a FEN onto an existing board.png (legacy companion to `solve`)."""
    from chessdiagram.artifacts import write_audit_file
    from chessdiagram.geometry import all_cells
    parsed, errors = parse_fen(args.fen)
    if parsed is None:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1
    report = load_report(args.board)
    board_path = Path(report.get("artifacts", {}).get("board") or
                      Path(args.board).parent / "board.png")
    if not board_path.is_file():
        return _print_error(f"board image not found: {board_path}")
    board = load_rgb(board_path)
    cells = all_cells(board.width, board.height)
    for cell in cells:
        cell.fen = parsed["grid"][cell.row][cell.col]
        cell.confidence = 1.0
        cell.source = "manual"
    write_audit_file(board, cells, [], args.out)
    print(f"wrote {args.out} - check every label against the printed piece")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("solve", help="full pipeline: boards -> cells -> OCR -> FEN -> audit")
    p.add_argument("image")
    p.add_argument("--out", required=True)
    p.add_argument("--board-index", type=int, help="0-based board index on a multi-board page")
    p.add_argument("--bbox", help="manual board box x0,y0,x1,y1 (skips board detection)")
    p.add_argument("--orientation", choices=["auto", "white", "black"], default="auto")
    p.add_argument("--flip", action="store_true", default=None,
                   help="force a 180-degree rotation (Black at the bottom)")
    p.add_argument("--conf", type=float, default=0.25, help="detector confidence floor")
    p.add_argument("--review-conf", type=float, default=0.75,
                   help="flag cells below this confidence")
    p.add_argument("--no-deskew", action="store_true")
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--turn", choices=["w", "b"], default=DEFAULT_TURN)
    p.add_argument("--castling", default=DEFAULT_CASTLING)
    p.add_argument("--ep", default=DEFAULT_EP)
    p.add_argument("--halfmove", type=int, default=DEFAULT_HALFMOVE)
    p.add_argument("--fullmove", type=int, default=DEFAULT_FULLMOVE)
    p.add_argument("--strict", action="store_true", help="exit 1 when the FEN is illegal")
    p.add_argument("--json", action="store_true")
    _add_model_args(p)
    p.set_defaults(func=cmd_solve)

    p = sub.add_parser("stage", help="detect board(s) and split cells without OCR")
    p.add_argument("image")
    p.add_argument("--out", required=True)
    p.add_argument("--board-index", type=int)
    p.add_argument("--bbox")
    p.add_argument("--orientation", choices=["auto", "white", "black"], default="auto")
    p.add_argument("--flip", action="store_true", default=None)
    p.add_argument("--no-deskew", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--turn", choices=["w", "b"], default=DEFAULT_TURN)
    p.add_argument("--castling", default=DEFAULT_CASTLING)
    p.add_argument("--ep", default=DEFAULT_EP)
    p.add_argument("--halfmove", type=int, default=DEFAULT_HALFMOVE)
    p.add_argument("--fullmove", type=int, default=DEFAULT_FULLMOVE)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--review-conf", type=float, default=0.75)
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--strict", action="store_true", help=argparse.SUPPRESS)
    _add_model_args(p)
    p.set_defaults(func=cmd_stage)

    p = sub.add_parser("read", help="re-run OCR on a staged board.json")
    p.add_argument("--board", required=True)
    p.add_argument("--out", help="defaults to the board.json directory")
    p.add_argument("--orientation", choices=["auto", "white", "black"], default="auto")
    p.add_argument("--flip", action="store_true", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--turn", choices=["w", "b"], default=DEFAULT_TURN)
    p.add_argument("--castling", default=DEFAULT_CASTLING)
    p.add_argument("--ep", default=DEFAULT_EP)
    p.add_argument("--halfmove", type=int, default=DEFAULT_HALFMOVE)
    p.add_argument("--fullmove", type=int, default=DEFAULT_FULLMOVE)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--review-conf", type=float, default=0.75)
    p.add_argument("--no-deskew", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--board-index", type=int, help=argparse.SUPPRESS)
    p.add_argument("--bbox", help=argparse.SUPPRESS)
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--strict", action="store_true", help=argparse.SUPPRESS)
    _add_model_args(p)
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("apply", help="apply visual corrections to flagged squares")
    p.add_argument("--board", required=True)
    p.add_argument("--set", required=True, help="comma list, e.g. e4=Q,d5=.")
    p.add_argument("--note", help="record why the correction was made")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("review", help="draw the flagged cells with their alternatives")
    p.add_argument("--board", required=True)
    p.add_argument("--squares", help="comma list; defaults to the report's review set")
    p.add_argument("--out")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("inspect", help="zoom specific squares (alias of review --squares)")
    p.add_argument("--board", required=True)
    p.add_argument("--squares", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("check", help="validate a FEN and print the board")
    p.add_argument("fen")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("annotate", help="stamp a FEN onto board.png for an audit")
    p.add_argument("--board", required=True)
    p.add_argument("--fen", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_annotate)

    p = sub.add_parser("render", help="draw a FEN as a labeled board image")
    p.add_argument("fen")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("compare", help="square-by-square diff of two ledgers or FENs")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("grid", help="pixel-grid overlay for manual bbox selection")
    p.add_argument("image")
    p.add_argument("--out")
    p.add_argument("--step", type=int, default=50)
    p.set_defaults(func=cmd_grid)

    p = sub.add_parser("write-ledger", help="write an 8x8 ledger, validating its format")
    p.add_argument("--out", required=True)
    p.add_argument("--rows", required=True,
                   help="8 rows separated by commas or newlines, rank 8 first")
    p.set_defaults(func=cmd_write_ledger)

    p = sub.add_parser("counts", help="piece inventory of a ledger")
    p.add_argument("ledger")
    p.set_defaults(func=cmd_counts)

    p = sub.add_parser("fen", help="assemble a FEN from a ledger")
    p.add_argument("--ledger", required=True)
    p.add_argument("--turn", choices=["w", "b"], default=DEFAULT_TURN)
    p.add_argument("--castling", default=DEFAULT_CASTLING)
    p.add_argument("--ep", default=DEFAULT_EP)
    p.add_argument("--halfmove", type=int, default=DEFAULT_HALFMOVE)
    p.add_argument("--fullmove", type=int, default=DEFAULT_FULLMOVE)
    p.set_defaults(func=cmd_fen)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
