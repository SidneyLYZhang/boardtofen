"""Model-backed chess diagram recognition for chess-diagram-to-fen.

The package wraps the 2d-chess-ocr YOLO detector (ONNX), board/cell geometry,
FEN assembly, and python-chess validation. See THIRD_PARTY_NOTICES.md for
attribution and licensing.
"""
from __future__ import annotations

__version__ = "2.0.0"
__all__ = ["__version__"]
