"""Shared constants: class ids, FEN mappings, colours, defaults."""
from __future__ import annotations

from pathlib import Path

VERSION = "2.0.0"
SCHEMA = "chess-diagram-to-fen/2"

# ------------------------------------------------------------------ 2d-chess-ocr
# The detector was exported with this exact class order. Keep it in sync with
# https://github.com/AndrewSpano/2d-chess-ocr (chess_ocr_detection.py).
CLASS_NAMES: dict[int, str] = {
    0: "chessboard",
    1: "black_pawn",
    2: "black_rook",
    3: "black_bishop",
    4: "black_knight",
    5: "black_king",
    6: "black_queen",
    7: "white_pawn",
    8: "white_rook",
    9: "white_bishop",
    10: "white_knight",
    11: "white_king",
    12: "white_queen",
    13: "rank_one_id",
    14: "last_move_start_tile",
    15: "last_move_end_tile",
}
CLASS_IDS = {name: cid for cid, name in CLASS_NAMES.items()}
BOARD_CLASS_ID = 0
PIECE_CLASS_IDS = frozenset(range(1, 13))
BLACK_PIECE_IDS = frozenset(range(1, 7))
WHITE_PIECE_IDS = frozenset(range(7, 13))
RANK_ONE_CLASS_ID = 13
LAST_MOVE_START_CLASS_ID = 14
LAST_MOVE_END_CLASS_ID = 15

PIECE_TO_FEN: dict[str, str] = {
    "black_pawn": "p", "black_rook": "r", "black_bishop": "b",
    "black_knight": "n", "black_king": "k", "black_queen": "q",
    "white_pawn": "P", "white_rook": "R", "white_bishop": "B",
    "white_knight": "N", "white_king": "K", "white_queen": "Q",
}
FEN_TO_PIECE = {v: k for k, v in PIECE_TO_FEN.items()}
FEN_PIECES = frozenset(FEN_TO_PIECE)

PIECE_GLYPHS = {
    "k": "\u265a", "q": "\u265b", "r": "\u265c",
    "b": "\u265d", "n": "\u265e", "p": "\u265f",
}

# ------------------------------------------------------------------ FEN defaults
DEFAULT_TURN = "w"
DEFAULT_CASTLING = "-"
DEFAULT_EP = "-"
DEFAULT_HALFMOVE = 0
DEFAULT_FULLMOVE = 1
DEFAULT_METADATA_SOURCE = "default"

# ------------------------------------------------------------------ model store
SCRIPT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = SCRIPT_DIR / "models" / "2d-chess-ocr"
MODEL_REPO = "AndrewSpano/2d-chess-ocr"
MODEL_HF_URL = "https://huggingface.co/AndrewSpano/2d-chess-ocr"

# sha256 and sizes are the Hugging Face LFS oids; verified before first use.
MODEL_SPECS: dict[str, dict] = {
    "m": {
        "filename": "yolo26m-finetuned.onnx",
        "sha256": "a8e78afa8e00cd7ee39a941f888327bd85a12c3cf5c2140a4fa882ea3f7abff7",
        "size": 81_764_872,
        "url": f"{MODEL_HF_URL}/resolve/main/yolo26m-finetuned.onnx",
        "note": "YOLO26-m, the accurate default (81.8 MB)",
    },
    "n": {
        "filename": "yolo26n-finetuned.onnx",
        "sha256": "d098a71847fac9b98e9cfcfde5854cee8b518d96503b2f006aa561f8b627db39",
        "size": 9_817_138,
        "url": f"{MODEL_HF_URL}/resolve/main/yolo26n-finetuned.onnx",
        "note": "YOLO26-n, the small fallback (9.8 MB)",
    },
}
DEFAULT_VARIANT = "m"

# ------------------------------------------------------------------ palette
LIGHT = (241, 218, 181)
DARK = (181, 136, 99)
GRID_RED = (225, 40, 40)
LABEL = (180, 25, 35)
INK = (32, 32, 32)
MUTED = (100, 100, 100)
PAPER = (252, 250, 244)
WHITE_PIECE_COLOUR = (190, 35, 35)
BLACK_PIECE_COLOUR = (30, 70, 190)
REVIEW_COLOUR = (230, 150, 0)
