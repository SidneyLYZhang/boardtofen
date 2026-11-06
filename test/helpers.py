"""Shared paths and synthetic detections for the chess-diagram tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".dsh" / "skills" / "chess-diagram-to-fen"
SCRIPTS = SKILL / "scripts"
MODEL_DIR = SCRIPTS / "models" / "2d-chess-ocr"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from chessdiagram.constants import CLASS_IDS  # noqa: E402
from chessdiagram.detector import Detection  # noqa: E402
from chessdiagram.geometry import CellCandidate  # noqa: E402

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"
START_ROWS = [
    "rnbqkbnr",
    "pppppppp",
    "........",
    "........",
    "........",
    "........",
    "PPPPPPPP",
    "RNBQKBNR",
]

FEN_TO_NAME = {
    "K": "white_king", "Q": "white_queen", "R": "white_rook",
    "B": "white_bishop", "N": "white_knight", "P": "white_pawn",
    "k": "black_king", "q": "black_queen", "r": "black_rook",
    "b": "black_bishop", "n": "black_knight", "p": "black_pawn",
}


def has_onnxruntime() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def model_path() -> Path | None:
    for name in ("yolo26m-finetuned.onnx", "yolo26n-finetuned.onnx"):
        path = MODEL_DIR / name
        if path.is_file():
            return path
    return None


def piece_detection(piece: str, square: str, *, conf: float = 0.9) -> Detection:
    """A detection centred on an algebraic square in an 800x800 board."""
    file_i = ord(square[0].lower()) - ord("a")
    row = 8 - int(square[1])
    cx, cy = file_i * 100 + 50, row * 100 + 50
    name = FEN_TO_NAME[piece]
    return Detection(CLASS_IDS[name], name, conf, (cx - 20, cy - 20, cx + 20, cy + 20))


def board_detections(rows: list[str], *, conf: float = 0.9) -> list[Detection]:
    dets = []
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch != ".":
                square = f"{chr(ord('a') + c)}{8 - r}"
                dets.append(piece_detection(ch, square, conf=conf))
    return dets


def empty_mapping() -> dict[str, list[CellCandidate]]:
    return {f"{chr(ord('a') + c)}{8 - r}": [] for r in range(8) for c in range(8)}


def mapping_with(square: str, symbols: list[tuple[str, float]]) -> dict[str, list[CellCandidate]]:
    out = empty_mapping()
    for fen, conf in symbols:
        name = FEN_TO_NAME[fen]
        out[square].append(CellCandidate(fen, name, conf, (0, 0, 10, 10), "test"))
    return out
