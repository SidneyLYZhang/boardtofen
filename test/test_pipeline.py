"""Unit tests for report-level review selection."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test.helpers import ROOT

from chessdiagram.geometry import CellPrediction
from chessdiagram.pipeline import _review_squares, apply_changes


def _cell(square: str, conf: float, flags: list[str] | None = None,
          source: str = "model") -> CellPrediction:
    return CellPrediction(square=square, row=0, col=0, crop=(0, 0, 1, 1),
                          fen="P", confidence=conf, source=source,
                          flags=flags or [])


class ReviewSelectionTests(unittest.TestCase):
    def test_review_conf_controls_low_confidence(self):
        cells = [_cell("e4", 0.70), _cell("e5", 0.90)]
        self.assertEqual(_review_squares(cells, [], 0.75), ["e4"])
        self.assertEqual(_review_squares(cells, [], 0.50), [])

    def test_pass_disagreement_always_reviewed(self):
        cells = [_cell("e4", 0.99, ["pass-disagreement"])]
        self.assertEqual(_review_squares(cells, [], 0.75), ["e4"])

    def test_manual_and_suspects(self):
        cells = [_cell("e4", 0.99, [], source="manual")]
        self.assertEqual(_review_squares(cells, ["d5"], 0.75), ["d5"])

    def test_apply_rejects_staged_report(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "test") as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps({"cells": {}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "staged without OCR"):
                apply_changes(path, {"e2": "P"})


if __name__ == "__main__":
    unittest.main()
