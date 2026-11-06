"""End-to-end tests. Skipped unless ONNX Runtime and the model are installed."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from test.helpers import ROOT, START_FEN, has_onnxruntime, model_path

from PIL import Image

SKIP_REASON = "ONNX Runtime and the 2d-chess-ocr model are required"


@unittest.skipUnless(has_onnxruntime() and model_path(), SKIP_REASON)
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from chessdiagram.ledger import cmd_render
        from chessdiagram.pipeline import SolveOptions, solve

        cls.solve = staticmethod(solve)
        cls.Options = SolveOptions
        cls.tmp = Path(tempfile.mkdtemp(prefix=".chess-test-", dir=ROOT / "test"))
        try:
            cls.model = model_path()
            start = cls.tmp / "start.png"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cmd_render(argparse.Namespace(fen=START_FEN, out=str(start)))
            if code != 0 or not start.is_file():
                raise RuntimeError("could not render the starting position")
            cls.start = start
            cls.start_work = cls.tmp / "start-work"
            cls.report = cls._solve(start, cls.start_work)
        except Exception:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmp", Path()), ignore_errors=True)

    @classmethod
    def _solve(cls, image: Path, out: Path):
        opts = cls.Options(
            image=str(image), out=str(out), model=str(cls.model),
            allow_download=False, review_conf=0.75)
        return cls.solve(opts)

    def test_starting_position(self):
        self.assertTrue(self.report.get("ok"), self.report.get("summary"))
        self.assertEqual(self.report["fen"], START_FEN)
        self.assertTrue(self.report["validation"]["legal"])
        self.assertEqual(self.report["board"]["orientation"], "white")
        self.assertEqual(len(self.report["cells"]), 64)
        for key in ("audit", "cells_json", "cells_sheet", "cells"):
            with self.subTest(key=key):
                self.assertTrue(Path(self.report["artifacts"][key]).exists())

    def test_rotated_orientation(self):
        rotated = self.tmp / "start-rotated.png"
        with Image.open(self.start) as opened:
            opened.convert("RGB").transpose(
                Image.Transpose.ROTATE_180).save(rotated)
        report = self._solve(rotated, self.tmp / "rot-work")
        self.assertEqual(report["fen"], START_FEN)
        self.assertEqual(report["board"]["orientation"], "black")
        self.assertEqual(report["board"]["orientation_source"], "labels")

    def test_stage_with_manual_bbox_reads_labels(self):
        from chessdiagram.pipeline import stage
        rotated = self.tmp / "stage-rotated.png"
        with Image.open(self.start) as opened:
            opened.convert("RGB").transpose(
                Image.Transpose.ROTATE_180).save(rotated)
        report = stage(self.Options(
            image=str(rotated), out=str(self.tmp / "stage-bbox"),
            model=str(self.model), bbox=(60, 60, 860, 860),
            allow_download=False))
        self.assertEqual(report["board"]["orientation"], "black")
        self.assertEqual(report["board"]["orientation_source"], "labels")

    def test_read_keeps_metadata(self):
        from chessdiagram.pipeline import read_board
        report = self.solve(self.Options(
            image=str(self.start), out=str(self.tmp / "meta-work"),
            model=str(self.model), allow_download=False,
            turn="b", castling="KQkq", metadata_source="user"))
        self.assertTrue(report["fen"].endswith("b KQkq - 0 1"), report["fen"])
        reread = read_board(report["artifacts"]["report"], self.Options(
            image="", out=str(self.tmp / "meta-read"),
            model=str(self.model), allow_download=False))
        self.assertTrue(reread["fen"].endswith("b KQkq - 0 1"), reread["fen"])

    def test_manual_correction_roundtrip(self):
        from chessdiagram.pipeline import apply_changes
        board = self.start_work / "board.json"
        try:
            removed = apply_changes(board, {"e2": "."}, "integration test")
            self.assertIn("PPPP1PPP", removed["fen"])
            self.assertEqual(removed["cells"]["e2"]["name"], "empty")
            self.assertTrue(removed["cells"]["a8"]["candidates"],
                            "apply must not wipe untouched cell candidates")
            cells_json = json.loads(
                Path(removed["artifacts"]["cells_json"]).read_text(encoding="utf-8"))
            self.assertEqual(cells_json["cells"]["e2"]["fen"], ".")
        finally:
            restored = apply_changes(board, {"e2": "P"}, "test cleanup")
        self.assertEqual(restored["fen"], START_FEN)
        self.assertEqual(restored["cells"]["e2"]["name"], "white_pawn")


if __name__ == "__main__":
    unittest.main()
