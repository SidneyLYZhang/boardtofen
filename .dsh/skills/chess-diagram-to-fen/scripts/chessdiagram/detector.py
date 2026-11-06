"""ONNX inference for the 2d-chess-ocr YOLO26 detector, plus board search.

The exported model accepts one 640x640 RGB letterboxed image and returns
``[1, 300, 6]`` rows of ``x1, y1, x2, y2, confidence, class_id``.  A standard
Ultralytics ``[1, 4 + nc, N]`` export is also decoded, so a re-export with
dynamic or non-NMS output still works.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageOps

from .constants import BOARD_CLASS_ID, CLASS_NAMES, MODEL_SPECS
from .imaging import letterbox


class DetectorError(RuntimeError):
    pass


@dataclass
class Detection:
    cls_id: int
    name: str
    conf: float
    xyxy: tuple[float, float, float, float]
    source: str = ""

    @property
    def center(self) -> tuple[float, float]:
        return ((self.xyxy[0] + self.xyxy[2]) / 2.0,
                (self.xyxy[1] + self.xyxy[3]) / 2.0)

@dataclass
class BoardCandidate:
    bbox: tuple[float, float, float, float]
    conf: float
    source: str = "page"
    area: float = 0.0

    def to_dict(self) -> dict:
        return {
            "bbox": [round(float(v), 1) for v in self.bbox],
            "conf": round(float(self.conf), 3),
            "source": self.source,
            "area": round(float(self.area), 1),
        }


@dataclass
class BoardSearch:
    boards: list[BoardCandidate] = field(default_factory=list)
    detections: list[Detection] = field(default_factory=list)
    method: str = "model"
    notes: list[str] = field(default_factory=list)


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = ((a[2] - a[0]) * (a[3] - a[1])
          + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / ua if ua > 0 else 0.0


def nms(dets: list[Detection], iou_thr: float = 0.5) -> list[Detection]:
    kept: list[Detection] = []
    for det in sorted(dets, key=lambda d: -d.conf):
        if all(_iou(det.xyxy, other.xyxy) < iou_thr for other in kept):
            kept.append(det)
    return kept


class Detector:
    """A thin ONNX Runtime wrapper, with the 2d-chess-ocr postprocessing."""

    def __init__(self, model_path: str | Path, conf: float = 0.25,
                 iou: float = 0.5, threads: int = 0,
                 providers: Sequence[str] | None = None):
        self.model_path = Path(model_path)
        self.conf = float(conf)
        self.iou = float(iou)
        self.threads = int(threads)
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - depends on install
            raise DetectorError(
                "onnxruntime is not installed. Run: "
                "python -m pip install -r requirements.txt") from exc

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if self.threads > 0:
            options.intra_op_num_threads = self.threads
        options.log_severity_level = 3
        available = ort.get_available_providers()
        if providers:
            wanted = list(providers)
        elif "CUDAExecutionProvider" in available:
            wanted = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            wanted = ["CPUExecutionProvider"]
        try:
            self.session = ort.InferenceSession(
                str(self.model_path), sess_options=options, providers=wanted)
        except Exception as exc:
            raise DetectorError(f"could not load {self.model_path}: {exc}") from exc
        self.providers = self.session.get_providers()
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape
        self.output_shape = self.session.get_outputs()[0].shape
        self.variant = next(
            (v for v, spec in MODEL_SPECS.items()
             if spec["filename"] == self.model_path.name), "custom")

    def detect(self, image: Image.Image, source: str = "",
               conf: float | None = None) -> list[Detection]:
        """Run inference on a PIL image; boxes are in ``image`` coordinates."""
        rgb = ImageOps.autocontrast(image.convert("RGB"), cutoff=1)
        canvas, scale, pad_x, pad_y = letterbox(rgb, 640, 114)
        array = np.asarray(canvas, dtype=np.float32) / 255.0
        tensor = array.transpose(2, 0, 1)[None, ...]
        try:
            outputs = self.session.run([self.output_name], {self.input_name: tensor})
        except Exception as exc:
            raise DetectorError(f"ONNX inference failed: {exc}") from exc
        dets = self._decode(outputs[0], image.size, scale, pad_x, pad_y,
                            self.conf if conf is None else conf)
        for det in dets:
            det.source = source
        return dets

    # ------------------------------------------------------------------ decode
    def _decode(self, output: np.ndarray, image_size: tuple[int, int],
                scale: float, pad_x: float, pad_y: float,
                conf_thr: float) -> list[Detection]:
        arr = np.asarray(output)
        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim != 2:
            raise DetectorError(f"unexpected ONNX output shape {output.shape}")
        if arr.shape[-1] == 6:
            rows = arr
            cand = [
                (float(r[4]), int(round(float(r[5]))),
                 float(r[0]), float(r[1]), float(r[2]), float(r[3]))
                for r in rows if float(r[4]) >= conf_thr
            ]
        else:
            nc = len(CLASS_NAMES)
            if arr.shape[0] == 4 + nc and arr.shape[1] != 4 + nc:
                arr = arr.T
            elif arr.shape[-1] != 4 + nc:
                raise DetectorError(
                    f"model output has {arr.shape} columns; expected "
                    f"{4 + len(CLASS_NAMES)} class scores or 6 end-to-end fields")
            boxes = arr[:, :4]
            scores = arr[:, 4:4 + nc]
            cls_ids = scores.argmax(axis=1)
            confs = scores[np.arange(len(scores)), cls_ids]
            keep = confs >= conf_thr
            boxes, cls_ids, confs = boxes[keep], cls_ids[keep], confs[keep]
            # Standard Ultralytics detection exports are cx, cy, w, h.  The
            # end-to-end 6-field export above is the one that carries xyxy.
            cx, cy, bw, bh = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
            x1, y1 = cx - bw / 2.0, cy - bh / 2.0
            x2, y2 = cx + bw / 2.0, cy + bh / 2.0
            cand = [(float(c), int(k), float(a), float(b), float(cc), float(d))
                    for c, k, a, b, cc, d in zip(confs, cls_ids, x1, y1, x2, y2)]

        # Some exports return normalized coordinates. Pixel coordinates for a
        # 640-px input are always well above 2; normalized ones are not.
        max_coord = max((max(abs(v) for v in row[2:]) for row in cand), default=0.0)
        normalized = 0.0 < max_coord <= 2.0
        width, height = image_size
        dets: list[Detection] = []
        for conf, cls_id, x1, y1, x2, y2 in cand:
            if cls_id not in CLASS_NAMES:
                continue
            if normalized:
                x1, x2, y1, y2 = x1 * 640, x2 * 640, y1 * 640, y2 * 640
            x1 = (x1 - pad_x) / scale
            x2 = (x2 - pad_x) / scale
            y1 = (y1 - pad_y) / scale
            y2 = (y2 - pad_y) / scale
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            x1, x2 = max(0.0, min(x1, width)), max(0.0, min(x2, width))
            y1, y2 = max(0.0, min(y1, height)), max(0.0, min(y2, height))
            if x2 - x1 < 1.0 or y2 - y1 < 1.0:
                continue
            dets.append(Detection(cls_id, CLASS_NAMES[cls_id], conf,
                                  (x1, y1, x2, y2)))
        boards = [d for d in dets if d.cls_id == BOARD_CLASS_ID]
        rest = [d for d in dets if d.cls_id != BOARD_CLASS_ID]
        return nms(boards, self.iou) + rest

    def describe(self) -> dict:
        spec = MODEL_SPECS.get(self.variant)
        return {
            "path": str(self.model_path.resolve()),
            "variant": self.variant,
            "sha256": spec["sha256"] if spec else None,
            "size": self.model_path.stat().st_size if self.model_path.exists() else None,
            "providers": list(self.providers),
            "input": {"name": self.input_name, "shape": list(self.input_shape)},
            "output": {"name": self.output_name, "shape": list(self.output_shape)},
        }


# -------------------------------------------------------------------- board search
def _board_filter(dets: Iterable[Detection], width: int, height: int) -> list[BoardCandidate]:
    image_area = float(max(1, width * height))
    out: list[BoardCandidate] = []
    for det in dets:
        if det.cls_id != BOARD_CLASS_ID:
            continue
        x0, y0, x1, y1 = det.xyxy
        w, h = x1 - x0, y1 - y0
        if w < 48 or h < 48:
            continue
        aspect = w / h if h else 0
        if not 0.55 <= aspect <= 1.8:
            continue
        area = w * h
        if area / image_area < 0.003:
            continue
        out.append(BoardCandidate((x0, y0, x1, y1), det.conf, det.source, area))
    kept = nms([Detection(BOARD_CLASS_ID, "chessboard", b.conf, b.bbox, b.source)
                for b in out], 0.5)
    return [
        BoardCandidate(d.xyxy, d.conf, d.source,
                       (d.xyxy[2] - d.xyxy[0]) * (d.xyxy[3] - d.xyxy[1]))
        for d in kept
    ]


def _tiles(width: int, height: int) -> list[tuple[int, int, int, int]]:
    tw, th = int(width * 0.62), int(height * 0.62)
    xs = sorted({0, max(0, (width - tw) // 2), max(0, width - tw)})
    ys = sorted({0, max(0, (height - th) // 2), max(0, height - th)})
    boxes = []
    for y in ys:
        for x in xs:
            boxes.append((x, y, min(width, x + tw), min(height, y + th)))
    return boxes


def _map_detection(det: Detection, dx: float, dy: float) -> Detection:
    x0, y0, x1, y1 = det.xyxy
    return Detection(det.cls_id, det.name, det.conf,
                     (x0 + dx, y0 + dy, x1 + dx, y1 + dy), det.source)


def detect_boards(detector: Detector | None, image: Image.Image) -> BoardSearch:
    """Find every 8x8 board on the page, using tiles and classical CV as fallbacks."""
    width, height = image.size
    all_dets: list[Detection] = []
    notes: list[str] = []
    method = "model"

    if detector is not None:
        page_dets = detector.detect(image, source="page")
        all_dets.extend(page_dets)
        boards = _board_filter(page_dets, width, height)
        if not boards and min(width, height) >= 240:
            notes.append("page pass found no board; tried overlapping tiles")
            method = "model-tiles"
            for i, (x0, y0, x1, y1) in enumerate(_tiles(width, height)):
                tile = image.crop((x0, y0, x1, y1))
                if tile.width < 64 or tile.height < 64:
                    continue
                for det in detector.detect(tile, source=f"tile{i}"):
                    mapped = _map_detection(det, x0, y0)
                    all_dets.append(mapped)
            boards = _board_filter(
                [d for d in all_dets if d.source.startswith("tile")], width, height)
        if boards:
            return BoardSearch(_sort_boards(boards), all_dets, method, notes)

    # Last resort: the projection-based detector from v1.  It is weaker on
    # book scans, but it needs no model and sometimes saves a clean screenshot.
    cv_box = _detect_board_cv(image)
    if cv_box is not None:
        notes.append("used classical CV fallback")
        w = cv_box[2] - cv_box[0]
        h = cv_box[3] - cv_box[1]
        board = BoardCandidate(cv_box, 0.1, "cv", w * h)
        return BoardSearch([board], all_dets, "cv", notes)

    return BoardSearch([], all_dets, "none", notes)


def _sort_boards(boards: list[BoardCandidate]) -> list[BoardCandidate]:
    return sorted(boards, key=lambda b: (round(b.bbox[1] / 40.0), b.bbox[0]))


def select_board(boards: list[BoardCandidate], index: int | None = None
                 ) -> tuple[BoardCandidate, list[BoardCandidate]]:
    if not boards:
        raise DetectorError("no chessboard found")
    ordered = _sort_boards(list(boards))
    if index is None:
        chosen = max(ordered, key=lambda b: (b.area, b.conf))
    else:
        if not 0 <= index < len(ordered):
            raise DetectorError(
                f"board index {index} out of range; found {len(ordered)} board(s)")
        chosen = ordered[index]
    return chosen, ordered


# -------------------------------------------------------------------- CV fallback
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


def _find_grid(score: np.ndarray, min_dim: float):
    peaks = _peaks(score, max(3, int(0.03 * min_dim)), rel=0.10, max_n=100)
    if len(peaks) < 3:
        return None
    span_lo, span_hi = 0.30 * min_dim, 0.99 * min_dim
    candidates: set[float] = set()
    for i in range(len(peaks)):
        for j in range(i + 1, len(peaks)):
            d = int(peaks[j] - peaks[i])
            for k in range(1, 9):
                step = d / k
                if span_lo / 8 <= step <= span_hi / 8:
                    candidates.add(round(step, 2))
    if not candidates:
        return None
    top = float(score.max())
    best = None
    for step in candidates:
        if 8 * step < span_lo or 8 * step > span_hi:
            continue
        for start in peaks:
            if start + 8 * step >= len(score):
                continue
            total = hits = 0.0
            for k in range(9):
                p = start + k * step
                lo = max(0, int(p - 0.10 * step))
                hi = min(len(score), int(p + 0.10 * step) + 1)
                v = float(score[lo:hi].max())
                total += v
                if v >= 0.45 * top:
                    hits += 1
            if hits < 7:
                continue
            val = total * (hits / 9.0) ** 2
            if best is None or val > best[0]:
                best = (val, step, int(start), int(hits))
    if best is None:
        return None
    _, step, start, _ = best
    refined = []
    for k in range(9):
        expect = start + k * step
        lo = max(0, int(expect - 0.16 * step))
        hi = min(len(score), int(expect + 0.18 * step) + 1)
        if hi <= lo:
            return None
        refined.append(lo + int(np.argmax(score[lo:hi])))
    a, b = np.polyfit(np.arange(9), np.asarray(refined, dtype=np.float64), 1)
    residual = float(np.max(np.abs(np.asarray(refined) - (a * np.arange(9) + b))))
    if a <= 2 or residual > 0.08 * a:
        return None
    return float(a), float(b), residual, refined


def _detect_board_cv(im: Image.Image):
    w, h = im.size
    scale = min(1.0, 1300.0 / max(w, h))
    small = im if scale >= 1.0 else im.resize(
        (max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    gray = np.asarray(small.convert("L"), dtype=np.uint8)
    col, row = _projection_scores(gray)
    min_dim = min(gray.shape)
    fx = _find_grid(col, min_dim)
    fy = _find_grid(row, min_dim)
    if not fx or not fy:
        return None
    ax, bx, _, _ = fx
    ay, by, _, _ = fy
    if not (0.12 * min_dim <= 8 * ax <= 1.02 * min_dim):
        return None
    if not (0.12 * min_dim <= 8 * ay <= 1.02 * min_dim):
        return None
    if abs(ax - ay) / max(ax, ay) > 0.09:
        return None
    x0, x1 = bx, bx + 8 * ax
    y0, y1 = by, by + 8 * ay
    if x0 < -2 or y0 < -2 or x1 > gray.shape[1] + 2 or y1 > gray.shape[0] + 2:
        return None
    inv = 1.0 / scale
    return (x0 * inv, y0 * inv, x1 * inv, y1 * inv)
