"""Board/cell geometry, model-to-grid assignment, and orientation evidence."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .constants import (
    FEN_TO_PIECE, PIECE_CLASS_IDS, PIECE_TO_FEN, RANK_ONE_CLASS_ID,
)
from .detector import Detection
from .imaging import cell_rect, square_name


@dataclass
class CellCandidate:
    fen: str
    name: str
    conf: float
    box: tuple[float, float, float, float]  # board-normalized pixels
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "fen": self.fen,
            "name": self.name,
            "conf": round(float(self.conf), 4),
            "box": [round(float(v), 1) for v in self.box],
            "source": self.source,
        }


@dataclass
class CellPrediction:
    square: str
    row: int
    col: int
    crop: tuple[int, int, int, int]
    fen: str = "."
    confidence: float = 1.0
    source: str = "model"
    candidates: list[CellCandidate] = field(default_factory=list)
    alternatives: list[CellCandidate] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return FEN_TO_PIECE.get(self.fen, "empty")

    def to_dict(self) -> dict:
        return {
            "square": self.square,
            "row": self.row,
            "col": self.col,
            "crop": list(self.crop),
            "fen": self.fen,
            "name": self.name,
            "confidence": round(float(self.confidence), 4),
            "source": self.source,
            "flags": list(self.flags),
            "candidates": [c.to_dict() for c in self.candidates],
            "alternatives": [c.to_dict() for c in self.alternatives],
        }


def all_cells(width: int, height: int) -> list[CellPrediction]:
    """Eight rows, rank 8 first; eight columns, file a first."""
    cells = []
    for row in range(8):
        for col in range(8):
            cells.append(CellPrediction(
                square=square_name(row, col),
                row=row,
                col=col,
                crop=cell_rect(row, col, width, height),
            ))
    return cells


def map_pass(detections: Iterable[Detection], origin: tuple[float, float],
             board_w: float, board_h: float, source: str = "") -> dict[str, list[CellCandidate]]:
    """Assign piece detections to squares for one inference pass.

    ``origin`` is the board's top-left corner in the inference crop, after any
    orientation flip.  The detection's *centre* decides the square, matching
    the 2d-chess-ocr convention and the old skill's "centre decides" rule.
    """
    mapping: dict[str, list[CellCandidate]] = {square_name(r, c): []
                                               for r in range(8) for c in range(8)}
    if board_w <= 0 or board_h <= 0:
        return mapping
    ox, oy = origin
    tol = 0.035
    for det in detections:
        if det.cls_id not in PIECE_CLASS_IDS:
            continue
        cx, cy = det.center
        u = (cx - ox) / board_w
        v = (cy - oy) / board_h
        if not (-tol <= u <= 1 + tol and -tol <= v <= 1 + tol):
            continue
        col = max(0, min(7, int(math.floor(u * 8))))
        row = max(0, min(7, int(math.floor(v * 8))))
        box = (det.xyxy[0] - ox, det.xyxy[1] - oy,
               det.xyxy[2] - ox, det.xyxy[3] - oy)
        mapping[square_name(row, col)].append(CellCandidate(
            fen=PIECE_TO_FEN[det.name],
            name=det.name,
            conf=float(det.conf),
            box=box,
            source=source or det.source,
        ))
    for square in mapping:
        mapping[square].sort(key=lambda c: -c.conf)
    return mapping


def _dedupe(cands: Sequence[CellCandidate]) -> list[CellCandidate]:
    """Keep the best detection per FEN symbol, preserving order by confidence."""
    best: dict[str, CellCandidate] = {}
    for cand in cands:
        old = best.get(cand.fen)
        if old is None or cand.conf > old.conf:
            best[cand.fen] = cand
    return sorted(best.values(), key=lambda c: -c.conf)


def merge_passes(passes: Sequence[tuple[str, dict[str, list[CellCandidate]]]],
                 review_conf: float = 0.75) -> list[CellPrediction]:
    """Fuse several independent passes into one prediction per square."""
    cells: list[CellPrediction] = []
    for row in range(8):
        for col in range(8):
            square = square_name(row, col)
            cells.append(CellPrediction(square=square, row=row, col=col, crop=(0, 0, 0, 0)))

    for cell in cells:
        per_pass: list[tuple[str, list[CellCandidate]]] = []
        for name, mapping in passes:
            cands = mapping.get(cell.square, [])
            if cands:
                per_pass.append((name, cands))
        if not per_pass:
            cell.fen = "."
            cell.confidence = 1.0
            cell.source = "model"
            continue

        # Each pass's own top pick (after collapsing duplicate boxes of the
        # same class); the best picks then vote across passes.
        tops: list[CellCandidate] = []
        for _, cands in per_pass:
            tops.append(_dedupe(cands)[0])
        by_fen: dict[str, list[CellCandidate]] = {}
        for cand in tops:
            by_fen.setdefault(cand.fen, []).append(cand)
        ranked = sorted(
            by_fen.items(),
            key=lambda item: (max(c.conf for c in item[1])
                              + 0.08 * (len(item[1]) - 1),
                              max(c.conf for c in item[1])),
            reverse=True,
        )
        top_fen, top_group = ranked[0]
        top_conf = max(c.conf for c in top_group)
        support = len(top_group)
        confidence = top_conf if support >= 2 else top_conf * 0.85
        confidence = min(0.995, confidence)

        cell.fen = top_fen
        cell.confidence = confidence
        cell.candidates = _dedupe([c for _, cands in per_pass for c in cands])
        cell.alternatives = [c for c in cell.candidates if c.fen != top_fen]

        if support < 2:
            cell.flags.append("single-pass")
        if len(ranked) > 1:
            cell.flags.append("pass-disagreement")
        if confidence < review_conf:
            cell.flags.append("low-confidence")
        close = [c for c in cell.alternatives if c.conf >= top_conf - 0.12]
        if close:
            cell.flags.append("close-alternative")
    return cells


def grid_from_cells(cells: Sequence[CellPrediction]) -> list[list[str]]:
    grid = [["." for _ in range(8)] for _ in range(8)]
    for cell in cells:
        grid[cell.row][cell.col] = cell.fen
    return grid


def _robust_axis(values: Sequence[float], indices: Sequence[int],
                 guess_origin: float, guess_size: float) -> dict | None:
    """Fit ``value = origin + size * (index + 0.5)`` with outlier rejection."""
    vals = [float(v) for v in values]
    idx = [float(i) + 0.5 for i in indices]
    if len(vals) < 6 or len(set(indices)) < 2:
        return None
    import numpy as np
    keep = [True] * len(vals)
    a = b = 0.0
    for _ in range(5):
        xs = [idx[i] for i in range(len(vals)) if keep[i]]
        ys = [vals[i] for i in range(len(vals)) if keep[i]]
        if len(xs) < 4:
            return None
        try:
            a, b = np.polyfit(xs, ys, 1)
        except (TypeError, ValueError, np.linalg.LinAlgError):
            return None
        residuals = [abs(a * idx[i] + b - vals[i]) for i in range(len(vals))]
        threshold = max(1.0, 0.05 * abs(a))
        new_keep = [r <= threshold for r in residuals]
        if sum(new_keep) == sum(keep):
            break
        keep = new_keep
    used = int(sum(bool(k) for k in keep))
    residuals = [abs(a * idx[i] + b - vals[i]) for i in range(len(vals)) if keep[i]]
    median = sorted(residuals)[len(residuals) // 2] if residuals else 999.0
    return {
        "origin": float(b), "size": float(a), "used": used, "median": round(median, 3),
        "distinct": len({int(i) for i, k in zip(indices, keep) if k}),
        "guess_origin": round(float(guess_origin), 2),
        "guess_size": round(float(guess_size), 2),
    }


def refine_bbox_from_pieces(
        bbox: Sequence[float], detections: Iterable[Detection],
        min_pieces: int = 12) -> tuple[tuple[float, float, float, float], dict]:
    """Snap the board box to the lattice of detected piece centres.

    The detector's board box is usually within a percent, but scans and thick
    borders can shift it enough to put a boundary piece in the wrong cell.  The
    centres of 12+ pieces give a much tighter fit.  The fit is rejected unless
    it is close to the detector's box, so a few outliers cannot move the board.
    """
    x0, y0, x1, y1 = (float(v) for v in bbox)
    bw, bh = x1 - x0, y1 - y0
    if bw <= 0 or bh <= 0:
        return (x0, y0, x1, y1), {"applied": False, "reason": "empty box"}
    sx, sy = bw / 8.0, bh / 8.0
    cols: list[int] = []
    rows: list[int] = []
    xs: list[float] = []
    ys: list[float] = []
    pad = 0.03
    for det in detections:
        if det.cls_id not in PIECE_CLASS_IDS or det.conf < 0.35:
            continue
        cx, cy = det.center
        u, v = (cx - x0) / bw, (cy - y0) / bh
        if not (-pad <= u <= 1 + pad and -pad <= v <= 1 + pad):
            continue
        cols.append(max(0, min(7, int(math.floor(u * 8)))))
        rows.append(max(0, min(7, int(math.floor(v * 8)))))
        xs.append(cx)
        ys.append(cy)
    evidence: dict = {
        "applied": False, "pieces": len(xs), "old_bbox": [round(v, 1) for v in bbox],
    }
    if len(xs) < max(6, min_pieces):
        evidence["reason"] = f"only {len(xs)} piece centres"
        return (x0, y0, x1, y1), evidence
    fx = _robust_axis(xs, cols, x0, sx)
    fy = _robust_axis(ys, rows, y0, sy)
    evidence["fit_x"] = fx
    evidence["fit_y"] = fy
    if not fx or not fy:
        evidence["reason"] = "degenerate axis fit"
        return (x0, y0, x1, y1), evidence
    strong = (fx["used"] >= 20 and fy["used"] >= 20
              and fx["median"] <= 1.0 and fy["median"] <= 1.0
              and fx["distinct"] >= 4 and fy["distinct"] >= 4)
    tolerance = 0.12 if strong else 0.04
    checks = []
    for name, fit, guess_origin, guess_size, guess_end in (
            ("x", fx, x0, sx, x1), ("y", fy, y0, sy, y1)):
        size = fit["size"]
        origin = fit["origin"]
        end = origin + 8 * size
        checks.append(abs(size - guess_size) <= tolerance * guess_size)
        checks.append(abs(origin - guess_origin) <= tolerance * guess_size)
        checks.append(abs(end - guess_end) <= tolerance * guess_size)
        checks.append(fit["used"] >= max(6, min_pieces // 2))
        checks.append(fit["distinct"] >= 4)
        checks.append(fit["median"] <= max(1.5, 0.04 * abs(size)))
    if not all(checks):
        evidence["reason"] = "fit too far from the detector box"
        return (x0, y0, x1, y1), evidence
    if abs(fx["size"] - fy["size"]) / max(fx["size"], fy["size"]) > 0.06:
        evidence["reason"] = "fitted cells are not square"
        return (x0, y0, x1, y1), evidence
    new_bbox = (fx["origin"], fy["origin"],
                fx["origin"] + 8 * fx["size"], fy["origin"] + 8 * fy["size"])
    # A perfect fit can land at -4e-14 from floating point; allow a sub-pixel
    # overshoot and clamp it to the image edge.
    eps = 0.5
    if not (-eps <= new_bbox[0] < new_bbox[2]
            and -eps <= new_bbox[1] < new_bbox[3]):
        evidence["reason"] = "fit outside the image"
        return (x0, y0, x1, y1), evidence
    new_bbox = (max(0.0, new_bbox[0]), max(0.0, new_bbox[1]),
                new_bbox[2], new_bbox[3])
    evidence.update({
        "applied": True,
        "new_bbox": [round(v, 1) for v in new_bbox],
        "delta_px": [round(new_bbox[0] - x0, 1), round(new_bbox[1] - y0, 1),
                     round(new_bbox[2] - x1, 1), round(new_bbox[3] - y1, 1)],
    })
    return new_bbox, evidence


def label_evidence(detections: Iterable[Detection],
                   board_bbox: Sequence[float],
                   pad: float = 0.16) -> dict:
    """Read the printed rank-1 marker (class 13) around the board.

    A chess diagram labels rank 1 at the bottom when White is at the bottom.
    The detector only knows the digit ``1``; that is enough to orient the board.
    """
    x0, y0, x1, y1 = (float(v) for v in board_bbox)
    bw, bh = x1 - x0, y1 - y0
    if bw <= 0 or bh <= 0:
        return {"vote": "none", "bottom": 0.0, "top": 0.0, "detections": []}
    left, right = x0 - pad * bw, x1 + pad * bw
    top_limit, bottom_limit = y0 - pad * bh, y1 + pad * bh
    bottom = top = 0.0
    found = []
    for det in detections:
        if det.cls_id != RANK_ONE_CLASS_ID or det.conf < 0.20:
            continue
        cx, cy = det.center
        if not (left <= cx <= right and top_limit <= cy <= bottom_limit):
            continue
        rel_x = (cx - x0) / bw
        rel_y = (cy - y0) / bh
        # Rank labels live beside the board's left or right edge and within the
        # board's vertical span.  A diagram number "1." above the board must not
        # be mistaken for a rank-1 label.
        if not (rel_x <= 0.16 or rel_x >= 0.84):
            continue
        if not (-0.04 <= rel_y <= 1.04):
            continue
        found.append({
            "conf": round(float(det.conf), 3),
            "rel_x": round(float(rel_x), 3),
            "rel_y": round(float(rel_y), 3),
            "box": [round(float(v), 1) for v in det.xyxy],
        })
        if rel_y >= 0.80:
            bottom += det.conf
        elif rel_y <= 0.20:
            top += det.conf

    if not found:
        vote = "none"
    elif bottom >= 0.2 and bottom > top * 1.25:
        vote = "normal"
    elif top >= 0.2 and top > bottom * 1.25:
        vote = "flipped"
    else:
        vote = "ambiguous"
    return {
        "vote": vote,
        "bottom": round(bottom, 3),
        "top": round(top, 3),
        "detections": found,
    }


def evidence_from_pass(mapping: dict[str, list[CellCandidate]]) -> dict:
    """Summarize how strongly one orientation pass recognized real pieces."""
    pieces = [cands[0] for cands in mapping.values() if cands]
    count = sum(1 for c in pieces if c.conf >= 0.35)
    usable = [c for c in pieces if c.conf >= 0.35]
    mean = sum(c.conf for c in usable) / len(usable) if usable else 0.0
    weight = sum(max(0.0, c.conf - 0.25) for c in usable)
    return {
        "count": count,
        "mean_conf": round(mean, 4),
        "weight": round(weight, 3),
    }
