"""End-to-end pipeline: image -> board -> orientation -> 64 squares -> FEN -> audit."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from PIL import Image

from . import __version__
from .artifacts import (
    write_audit, write_cells, write_detection, write_overlay, write_review,
)
from .constants import (
    DEFAULT_CASTLING, DEFAULT_EP, DEFAULT_FULLMOVE, DEFAULT_HALFMOVE,
    DEFAULT_METADATA_SOURCE, DEFAULT_TURN, SCHEMA,
)
from .detector import (
    BoardCandidate, BoardSearch, Detector, DetectorError, detect_boards,
    select_board,
)
from .geometry import (
    CellPrediction, all_cells, evidence_from_pass, grid_from_cells,
    label_evidence, map_pass, merge_passes, refine_bbox_from_pieces,
)
from .imaging import (
    cell_rect, clamp_bbox, crop_with_margin, estimate_skew, load_rgb,
    normalized_board, rotate_working, save_json, square_index,
)
from .model_store import ensure_model
from .rules import fen_from_grid, orientation_penalty, validate_grid


@dataclass
class SolveOptions:
    image: str
    out: str
    board_index: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    orientation: str = "auto"          # auto | white | black
    flip: bool | None = None           # explicit override
    model: str | None = None
    variant: str = "auto"              # auto | m | n
    model_dir: str | None = None
    allow_download: bool = False
    mirror: str | None = None
    conf: float = 0.25
    review_conf: float = 0.75
    deskew: bool = True
    threads: int = 0
    turn: str = DEFAULT_TURN
    castling: str = DEFAULT_CASTLING
    ep: str = DEFAULT_EP
    halfmove: int = DEFAULT_HALFMOVE
    fullmove: int = DEFAULT_FULLMOVE
    metadata_source: str = DEFAULT_METADATA_SOURCE
    strict: bool = False


class BoardError(RuntimeError):
    pass


@dataclass
class OrientationResult:
    flip: bool
    source: str
    evidence: dict = field(default_factory=dict)
    pass_mapping: dict | None = None


def _now() -> float:
    return time.perf_counter()


def _prepare_image(opts: SolveOptions, out: Path) -> tuple[Image.Image, float, Path]:
    im = load_rgb(opts.image)
    skew = 0.0
    working = im
    if opts.deskew:
        skew = estimate_skew(im)
        if abs(skew) >= 0.5:
            working = rotate_working(im, skew)
    working_path = out / "working.png"
    working.save(working_path)
    return working, skew, working_path


def _build_detector(opts: SolveOptions) -> Detector:
    model_path = ensure_model(
        variant=opts.variant, model_path=opts.model, dest_dir=opts.model_dir,
        allow_download=opts.allow_download, mirror=opts.mirror)
    return Detector(model_path, conf=opts.conf, threads=opts.threads)


def _locate_board(detector: Detector | None, image: Image.Image,
                  opts: SolveOptions) -> tuple:
    """Resolve the selected board box, candidates, and label detections."""
    if opts.bbox:
        bbox = clamp_bbox(opts.bbox, image.width, image.height)
        boards = [BoardCandidate(bbox, 1.0, "manual",
                                 (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))]
        # A page pass is what lets printed rank labels settle orientation.
        page_dets = detector.detect(image, source="page") if detector else []
        search = BoardSearch(boards, page_dets, "manual", [])
        return bbox, boards, 0, search, {"applied": False, "reason": "manual bbox"}

    search = detect_boards(detector, image)
    if not search.boards:
        raise BoardError("no 8x8 chessboard detected")
    try:
        selected, ordered = select_board(search.boards, opts.board_index)
    except DetectorError as exc:
        raise BoardError(str(exc)) from exc
    bbox = clamp_bbox(selected.bbox, image.width, image.height)
    bbox, refine = refine_bbox_from_pieces(bbox, search.detections)
    bbox = clamp_bbox(bbox, image.width, image.height)
    return bbox, ordered, ordered.index(selected), search, refine


def _orientation_pass(detector: Detector, image: Image.Image, bbox: Sequence[float],
                      flip: bool, margin: float = 0.25) -> dict:
    crop, origin, bw, bh = crop_with_margin(image, bbox, margin, flip)
    dets = detector.detect(crop, source="orientation")
    mapping = map_pass(dets, origin, bw, bh, "orientation")
    cells = merge_passes([("orientation", mapping)])
    grid = grid_from_cells(cells)
    evidence = evidence_from_pass(mapping)
    evidence["penalty"] = orientation_penalty(grid)
    evidence["grid"] = grid
    evidence["mapping"] = mapping
    evidence["detections"] = len(dets)
    return evidence


def choose_orientation(detector: Detector, image: Image.Image,
                       bbox: Sequence[float], label: dict,
                       opts: SolveOptions) -> OrientationResult:
    if opts.flip is not None:
        return OrientationResult(bool(opts.flip), "user",
                                 {"flip": bool(opts.flip), "label": label})
    if opts.orientation in ("white", "black"):
        return OrientationResult(opts.orientation == "black", "user",
                                 {"orientation": opts.orientation, "label": label})

    normal = _orientation_pass(detector, image, bbox, False)
    flipped = _orientation_pass(detector, image, bbox, True)
    evidence = {
        "label": label,
        "normal": {k: v for k, v in normal.items() if k not in ("mapping", "grid")},
        "flipped": {k: v for k, v in flipped.items() if k not in ("mapping", "grid")},
    }

    normal_penalty = normal["penalty"]["penalty"]
    flipped_penalty = flipped["penalty"]["penalty"]
    vote = label.get("vote")

    if vote in ("normal", "flipped"):
        label_flip = vote == "flipped"
        chosen = flipped if label_flip else normal
        other = normal if label_flip else flipped
        # Printed labels are ground truth. If a stray diagram number "1." was
        # mistaken for one, the OCR evidence will disagree; keep the label but
        # warn so the operator can override with --orientation.
        conflict = (
            other["count"] >= 12
            and other["count"] >= 3.0 * max(1, chosen["count"])
            and other["penalty"]["penalty"] < chosen["penalty"]["penalty"])
        if conflict:
            evidence["warning"] = (
                "printed rank-1 label conflicts with strong OCR evidence; "
                "keeping the printed label — verify with --orientation")
        flip = label_flip
        source = "labels"
    elif normal_penalty != flipped_penalty:
        flip = flipped_penalty < normal_penalty
        source = "rules"
    else:
        normal_weight = normal["weight"]
        flipped_weight = flipped["weight"]
        normal_count = normal["count"]
        flipped_count = flipped["count"]
        if normal_count >= 4 and normal_weight > flipped_weight * 1.30:
            flip, source = False, "ocr"
        elif flipped_count >= 4 and flipped_weight > normal_weight * 1.30:
            flip, source = True, "ocr"
        else:
            flip, source = False, "default"
    chosen = flipped if flip else normal
    evidence["decision"] = {
        "flip": flip, "source": source,
        "normal_penalty": normal_penalty, "flipped_penalty": flipped_penalty,
        "normal_weight": normal["weight"], "flipped_weight": flipped["weight"]}
    return OrientationResult(flip, source, evidence, chosen["mapping"])


def _review_squares(cells: Sequence[CellPrediction], suspects: Sequence[str],
                    review_conf: float = 0.75) -> list[str]:
    review: set[str] = set()
    for cell in cells:
        if cell.source == "manual":
            continue
        hard = {"low-confidence", "single-pass", "close-alternative"} & set(cell.flags)
        if hard or cell.confidence < review_conf or "pass-disagreement" in cell.flags:
            review.add(cell.square)
    review.update(suspects)
    return sorted(review, key=square_index)


def _write_cell_images(board: Image.Image, cells: Sequence[CellPrediction],
                       out_dir: Path) -> dict[str, Path]:
    cells_dir = out_dir / "cells"
    if cells_dir.is_dir():
        for path in cells_dir.glob("*.png"):
            path.unlink()
    cells_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for cell in cells:
        x0, y0, x1, y1 = cell.crop
        tile = board.crop((x0, y0, x1, y1))
        tile = tile.resize((128, 128), Image.Resampling.LANCZOS)
        path = cells_dir / f"{cell.square}.png"
        tile.save(path)
        paths[cell.square] = path
    return paths


def _piece_counts(grid: Sequence[Sequence[str]]) -> dict:
    white = sum(1 for row in grid for ch in row if ch.isupper())
    black = sum(1 for row in grid for ch in row if ch.islower())
    return {"white": white, "black": black, "total": white + black}


def _summary(report: dict) -> str:
    board = report["board"]
    legal = "PASS" if report["validation"]["legal"] else "FAIL"
    review = ", ".join(report["review_squares"]) or "none"
    lines = [
        f"FEN  {report['fen']}",
        f"BOARD board {board['index']} | {board['width']:.0f}x{board['height']:.0f}px "
        f"| orientation {board['orientation']} ({board['orientation_source']}) "
        f"| {report['pieces']['total']} pieces",
        f"CHECK ARBITER: {legal} | python-chess: {report['validation']['python_chess']}",
        f"REVIEW {len(report['review_squares'])} square(s): {review}",
    ]
    warning = report["board"].get("orientation_evidence", {}).get("warning")
    if warning:
        lines.insert(2, f"WARNING {warning}")
    if report["validation"]["errors"]:
        for issue in report["validation"]["errors"]:
            squares = f" [{', '.join(issue['squares'])}]" if issue["squares"] else ""
            lines.append(f"  ERROR {issue['message']}{squares}")
    return "\n".join(lines)


def recognize(detector: Detector, working: Image.Image,
              bbox: Sequence[float], flip: bool, orientation_source: str,
              orientation_evidence: dict, boards: Sequence[BoardCandidate],
              selected_index: int, search: BoardSearch, out: Path,
              opts: SolveOptions, skew: float, working_path: Path,
              orientation_pass: dict | None = None,
              timings: dict | None = None,
              bbox_refinement: dict | None = None) -> dict:
    timings = timings or {}
    t = _now()
    bbox = clamp_bbox(bbox, working.width, working.height)
    board_img = normalized_board(working, bbox, flip)
    board_img.save(out / "board.png")
    bw, bh = board_img.size

    cells = all_cells(bw, bh)
    for cell in cells:
        cell.crop = cell_rect(cell.row, cell.col, bw, bh)

    passes: list[tuple[str, dict]] = []
    if orientation_pass:
        passes.append(("crop-0.25", orientation_pass))
    for margin in (0.15, 0.35):
        crop, origin, cw, ch = crop_with_margin(working, bbox, margin, flip)
        dets = detector.detect(crop, source=f"crop-{margin:.2f}")
        passes.append((f"crop-{margin:.2f}", map_pass(dets, origin, cw, ch,
                                                      f"crop-{margin:.2f}")))
    timings["ocr"] = round(_now() - t, 3)

    t = _now()
    merged = merge_passes(passes, review_conf=opts.review_conf)
    for cell in merged:
        cell.crop = cell_rect(cell.row, cell.col, bw, bh)
    grid = grid_from_cells(merged)
    fen = fen_from_grid(grid, opts.turn, opts.castling, opts.ep,
                        opts.halfmove, opts.fullmove)
    validation = validate_grid(grid, opts.turn, opts.castling, opts.ep)
    review = _review_squares(merged, validation.suspect_squares, opts.review_conf)
    timings["merge"] = round(_now() - t, 3)

    t = _now()
    cell_paths = _write_cell_images(board_img, merged, out)
    save_json(out / "cells.json", {
        "board": {"bbox": [round(float(v), 1) for v in bbox],
                  "flip": bool(flip), "width": bw, "height": bh},
        "cells": {cell.square: cell.to_dict() | {"file": str(cell_paths[cell.square])}
                  for cell in merged},
    })
    write_cells(board_img, merged, review, out / "cells.png")
    write_detection(board_img, merged, out / "detection.png")
    audit_paths = write_audit(board_img, merged, review, out)
    review_path = write_review(board_img, merged, review, out / "review.png")
    if review_path is None:
        (out / "review.png").unlink(missing_ok=True)
    write_overlay(working, boards, boards[selected_index], flip, out / "overlay.png")
    timings["artifacts"] = round(_now() - t, 3)

    (out / "fen.txt").write_text(fen + "\n", encoding="utf-8")

    report = {
        "schema": SCHEMA,
        "version": __version__,
        "image": str(Path(opts.image).resolve()),
        "working_image": str(working_path.resolve()),
        "fen": fen,
        "ok": True,
        "board": {
            "index": selected_index,
            "bbox": [round(float(v), 1) for v in bbox],
            "width": bw,
            "height": bh,
            "flip": bool(flip),
            "orientation": "black" if flip else "white",
            "orientation_source": orientation_source,
            "orientation_evidence": orientation_evidence,
            "skew": round(float(skew), 2),
            "boards": [b.to_dict() for b in boards],
            "method": search.method,
            "notes": list(search.notes),
            "bbox_refinement": bbox_refinement or {},
        },
        "metadata": {
            "turn": opts.turn,
            "castling": opts.castling,
            "ep": opts.ep,
            "halfmove": opts.halfmove,
            "fullmove": opts.fullmove,
            "source": opts.metadata_source,
        },
        "review_conf": opts.review_conf,
        "pieces": _piece_counts(grid),
        "validation": validation.to_dict(),
        "review_squares": review,
        "cells": {cell.square: cell.to_dict() | {"file": str(cell_paths[cell.square])}
                  for cell in merged},
        "model": detector.describe(),
        "passes": [name for name, _ in passes],
        "artifacts": {
            "board": str((out / "board.png").resolve()),
            "cells": str((out / "cells").resolve()),
            "cells_json": str((out / "cells.json").resolve()),
            "cells_sheet": str((out / "cells.png").resolve()),
            "detection": str((out / "detection.png").resolve()),
            "overlay": str((out / "overlay.png").resolve()),
            "review": str(review_path.resolve()) if review_path else None,
            "fen": str((out / "fen.txt").resolve()),
            "report": str((out / "report.json").resolve()),
            **{k: str(v.resolve()) for k, v in audit_paths.items()},
        },
        "timings": timings,
    }
    report["summary"] = _summary(report)
    save_json(out / "board.json", report)
    save_json(out / "report.json", report)
    return report


def solve(opts: SolveOptions) -> dict:
    t0 = _now()
    out = Path(opts.out)
    out.mkdir(parents=True, exist_ok=True)
    working, skew, working_path = _prepare_image(opts, out)

    try:
        detector = _build_detector(opts)
    except Exception as exc:
        return {
            "ok": False, "error": str(exc), "exit_code": 4,
            "summary": f"MODEL ERROR: {exc}",
        }

    try:
        bbox, boards, selected_index, search, refine = _locate_board(
            detector, working, opts)
    except BoardError as exc:
        return {
            "ok": False, "error": str(exc), "exit_code": 3,
            "summary": (
                f"BOARD ERROR: {exc}.\n"
                "Try a complete, axis-aligned crop, or pass --bbox x0,y0,x1,y1."),
        }

    label = label_evidence(search.detections, bbox)
    try:
        orientation = choose_orientation(detector, working, bbox, label, opts)
    except Exception as exc:
        return {
            "ok": False, "error": f"orientation failed: {exc}", "exit_code": 5,
            "summary": f"ORIENTATION ERROR: {exc}",
        }

    timings = {"prepare": round(_now() - t0, 3)}
    try:
        report = recognize(
            detector, working, bbox, orientation.flip,
            orientation.source, orientation.evidence, boards, selected_index,
            search, out, opts, skew, working_path, orientation.pass_mapping,
            timings, bbox_refinement=refine)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {
            "ok": False, "error": f"recognition failed: {exc}", "exit_code": 5,
            "summary": f"RECOGNITION ERROR: {exc}",
        }
    report["timings"]["total"] = round(_now() - t0, 3)
    report["summary"] = _summary(report)
    save_json(out / "board.json", report)
    save_json(out / "report.json", report)
    return report


def stage(opts: SolveOptions) -> dict:
    """Detect the board and write cropped cells, without recognizing pieces."""
    out = Path(opts.out)
    out.mkdir(parents=True, exist_ok=True)
    working, skew, working_path = _prepare_image(opts, out)
    detector = None
    model_note = ""
    try:
        detector = _build_detector(opts)
    except Exception as exc:
        model_note = f"no model: {exc}"

    try:
        bbox, boards, selected_index, search, refine = _locate_board(
            detector, working, opts)
    except BoardError as exc:
        return {"ok": False, "exit_code": 3,
                "summary": f"BOARD ERROR: {exc}"}

    label = label_evidence(search.detections, bbox)
    if opts.flip is not None:
        flip, source = bool(opts.flip), "user"
    elif opts.orientation in ("white", "black"):
        flip, source = opts.orientation == "black", "user"
    elif label.get("vote") == "flipped":
        flip, source = True, "labels"
    elif label.get("vote") == "normal":
        flip, source = False, "labels"
    else:
        flip, source = False, "default"

    board_img = normalized_board(working, bbox, flip)
    board_img.save(out / "board.png")
    cells = all_cells(*board_img.size)
    for cell in cells:
        cell.crop = cell_rect(cell.row, cell.col, board_img.width, board_img.height)
    _write_cell_images(board_img, cells, out)
    save_json(out / "cells.json", {
        "board": {"bbox": [round(float(v), 1) for v in bbox],
                  "flip": bool(flip), "width": board_img.width,
                  "height": board_img.height},
        "cells": {cell.square: cell.to_dict() for cell in cells},
    })
    write_cells(board_img, cells, [], out / "cells.png",
                title="64 cells — staged, no OCR")
    write_overlay(working, boards, boards[selected_index], flip, out / "overlay.png")
    report = {
        "ok": True,
        "schema": SCHEMA,
        "version": __version__,
        "image": str(Path(opts.image).resolve()),
        "working_image": str(working_path.resolve()),
        "fen": None,
        "board": {
            "index": selected_index,
            "bbox": [round(float(v), 1) for v in bbox],
            "width": board_img.width,
            "height": board_img.height,
            "flip": bool(flip),
            "orientation": "black" if flip else "white",
            "orientation_source": source,
            "orientation_evidence": {"label": label},
            "skew": round(float(skew), 2),
            "boards": [b.to_dict() for b in boards],
            "method": search.method,
            "notes": list(search.notes) + ([model_note] if model_note else []),
            "bbox_refinement": refine,
        },
        "cells": {cell.square: cell.to_dict() for cell in cells},
        "artifacts": {
            "board": str((out / "board.png").resolve()),
            "cells": str((out / "cells").resolve()),
            "cells_json": str((out / "cells.json").resolve()),
            "cells_sheet": str((out / "cells.png").resolve()),
            "overlay": str((out / "overlay.png").resolve()),
        },
    }
    report["summary"] = (
        f"STAGED board {selected_index} | {board_img.width}x{board_img.height}px "
        f"| orientation {report['board']['orientation']} ({source}) "
        f"| 64 cells in {out / 'cells'}")
    save_json(out / "board.json", report)
    return report


def read_board(board_json: str | Path, opts: SolveOptions) -> dict:
    """Re-run recognition on a board.json produced by solve/stage."""
    board_json = Path(board_json)
    old = load_report(board_json)
    out = Path(opts.out) if opts.out else board_json.parent
    out.mkdir(parents=True, exist_ok=True)
    working_path = Path(old["working_image"])
    working = load_rgb(working_path)
    board_info = old["board"]
    if opts.metadata_source == "default" and old.get("metadata"):
        md = old["metadata"]
        opts.turn = md.get("turn", opts.turn)
        opts.castling = md.get("castling", opts.castling)
        opts.ep = md.get("ep", opts.ep)
        opts.halfmove = int(md.get("halfmove", opts.halfmove))
        opts.fullmove = int(md.get("fullmove", opts.fullmove))
        opts.metadata_source = md.get("source", "report")
    bbox = clamp_bbox(board_info["bbox"], working.width, working.height)
    boards = [BoardCandidate(tuple(b["bbox"]), float(b.get("conf", 1.0)),
                             b.get("source", "reused"))
              for b in board_info.get("boards", [])]
    if not boards:
        boards = [BoardCandidate(bbox, 1.0, "reused",
                                 (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))]
    selected_index = min(int(board_info.get("index", 0)), len(boards) - 1)
    selected = boards[selected_index]

    if opts.flip is not None:
        flip, source = bool(opts.flip), "user"
    elif opts.orientation in ("white", "black"):
        flip, source = opts.orientation == "black", "user"
    else:
        flip = bool(board_info.get("flip", False))
        source = board_info.get("orientation_source", "report")
    evidence = {"reused": True, "label": board_info.get("orientation_evidence")}

    try:
        detector = _build_detector(opts)
    except Exception as exc:
        return {"ok": False, "exit_code": 4,
                "summary": f"MODEL ERROR: {exc}"}
    opts.image = old.get("image", str(working_path))
    search = BoardSearch(boards, [], "reused", [])
    timings = {}
    report = recognize(
        detector, working, bbox, flip, source, evidence, boards,
        selected_index, search, out, opts,
        float(board_info.get("skew", 0.0)), working_path, None, timings,
        bbox_refinement=board_info.get("bbox_refinement"))
    return report


def load_report(path: str | Path) -> dict:
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _candidate_from_dict(data: dict):
    from .geometry import CellCandidate
    return CellCandidate(
        fen=data.get("fen", "."), name=data.get("name", ""),
        conf=float(data.get("conf", 0.0)),
        box=tuple(data.get("box", (0, 0, 0, 0))),
        source=data.get("source", ""))


def _cells_from_report(report: dict, *, alternatives: bool = False,
                       candidates: bool = False) -> list[CellPrediction]:
    cells = []
    for name, info in sorted(report["cells"].items(),
                             key=lambda kv: (kv[1]["row"], kv[1]["col"])):
        cells.append(CellPrediction(
            square=name, row=info["row"], col=info["col"],
            crop=tuple(info.get("crop", (0, 0, 0, 0))),
            fen=info["fen"], confidence=info.get("confidence", 1.0),
            source=info.get("source", "model"), flags=list(info.get("flags", [])),
            candidates=[_candidate_from_dict(c) for c in info.get("candidates", [])]
            if candidates else [],
            alternatives=[_candidate_from_dict(c) for c in info.get("alternatives", [])]
            if alternatives else [],
        ))
    return cells


def _rebuild_from_report(report: dict, out: Path | None = None) -> dict:
    """Recompute FEN, validation, and review data after a manual correction."""
    cells = _cells_from_report(report, alternatives=True, candidates=True)
    grid = grid_from_cells(cells)
    md = report["metadata"]
    fen = fen_from_grid(grid, md["turn"], md["castling"], md["ep"],
                        int(md["halfmove"]), int(md["fullmove"]))
    validation = validate_grid(grid, md["turn"], md["castling"], md["ep"])
    report["fen"] = fen
    report["validation"] = validation.to_dict()
    report["review_squares"] = _review_squares(
        cells, validation.suspect_squares, float(report.get("review_conf", 0.75)))
    report["pieces"] = _piece_counts(grid)
    next_cells = {}
    for cell in cells:
        payload = cell.to_dict()
        previous = report["cells"].get(cell.square, {})
        if previous.get("file"):
            payload["file"] = previous["file"]
        next_cells[cell.square] = payload
    report["cells"] = next_cells
    report["summary"] = _summary(report)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "fen.txt").write_text(fen + "\n", encoding="utf-8")
        save_json(out / "report.json", report)
        save_json(out / "board.json", report)
    return report


def apply_changes(board_json: str | Path, changes: dict[str, str],
                  note: str = "") -> dict:
    board_json = Path(board_json)
    out = board_json.parent
    report = load_report(board_json)
    if "metadata" not in report or "fen" not in report:
        raise ValueError(
            "board.json is staged without OCR; run `solve` or `read` first")
    from .constants import FEN_PIECES, FEN_TO_PIECE
    for square, value in changes.items():
        square = square.strip().lower()
        square_index(square)  # validate
        if square not in report["cells"]:
            raise ValueError(f"unknown square {square!r}")
        value = value.strip()
        if value.lower() in ("empty", "none"):
            value = "."
        if value != "." and value not in FEN_PIECES:
            raise ValueError(f"bad piece symbol {value!r} (use KQRBNP/kqrbnp or .)")
        info = report["cells"][square]
        info["fen"] = value
        info["name"] = "empty" if value == "." else FEN_TO_PIECE[value]
        info["confidence"] = 1.0
        info["source"] = "manual"
        info["flags"] = ["manual-correction"]
        info["candidates"] = []
        info["alternatives"] = []
    if note:
        report.setdefault("corrections", []).append({
            "changes": dict(changes), "note": note,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
    report = _rebuild_from_report(report, out)
    board_img = None
    try:
        from .imaging import load_rgb
        board_img = load_rgb(out / "board.png")
    except Exception:
        pass
    if board_img is not None:
        cells = _cells_from_report(report)
        write_audit(board_img, cells, report["review_squares"], out)
        write_cells(board_img, cells, report["review_squares"], out / "cells.png")
        write_detection(board_img, cells, out / "detection.png")
        board_info = report.get("board", {})
        save_json(out / "cells.json", {
            "board": {
                "bbox": board_info.get("bbox"),
                "flip": board_info.get("flip", False),
                "width": board_img.width,
                "height": board_img.height,
            },
            "cells": report["cells"],
        })
        report.setdefault("artifacts", {})["cells_json"] = str(
            (out / "cells.json").resolve())
        review_path = out / "review.png"
        if report["review_squares"]:
            write_review(board_img, cells, report["review_squares"], review_path)
            report.setdefault("artifacts", {})["review"] = str(review_path.resolve())
        else:
            review_path.unlink(missing_ok=True)
            report.setdefault("artifacts", {})["review"] = None
    return report


def review_sheet(board_json: str | Path, squares: Sequence[str] | None,
                 out_path: str | Path | None = None) -> dict:
    board_json = Path(board_json)
    report = load_report(board_json)
    out = board_json.parent
    board_img = load_rgb(out / "board.png")
    cells = [CellPrediction(
        square=name, row=info["row"], col=info["col"], crop=tuple(info["crop"]),
        fen=info["fen"], confidence=info.get("confidence", 1.0),
        source=info.get("source", "model"), flags=list(info.get("flags", [])),
        alternatives=[_candidate_from_dict(c) for c in info.get("alternatives", [])],
    ) for name, info in sorted(report["cells"].items(),
                              key=lambda kv: (kv[1]["row"], kv[1]["col"]))]
    chosen = list(squares) if squares else list(report.get("review_squares", []))
    target = Path(out_path) if out_path else out / "review.png"
    path = write_review(board_img, cells, chosen, target)
    return {"ok": path is not None, "review": str(path) if path else None,
            "squares": chosen}
