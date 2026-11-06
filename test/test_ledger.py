"""Tests for the manual ledger CLI return codes."""
from __future__ import annotations

import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from test.helpers import ROOT

from chessdiagram.ledger import cmd_fen


class FenCommandTests(unittest.TestCase):
    def test_illegal_ledger_returns_nonzero(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "test") as tmp:
            ledger = Path(tmp) / "legal.txt"
            ledger.write_text(
                "........\n" * 6 + "...k....\n...K....\n", encoding="utf-8")
            args = argparse.Namespace(
                ledger=str(ledger), turn="w", castling="-", ep="-",
                halfmove=0, fullmove=1)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cmd_fen(args)
            self.assertEqual(code, 1)
            self.assertIn("ARBITER", err.getvalue())


if __name__ == "__main__":
    unittest.main()
