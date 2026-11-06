"""Unit tests for FEN syntax, validation, and orientation scoring."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from test.helpers import START_FEN, START_ROWS

from chessdiagram.rules import (
    fen_from_grid, flipped_grid, grid_counts, ledger_to_fen, orientation_penalty,
    parse_fen, parse_ledger, validate_fen,
)


class FenSyntaxTests(unittest.TestCase):
    def test_start_parses(self):
        parsed, errors = parse_fen(START_FEN)
        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["grid"], [list(row) for row in START_ROWS])
        self.assertEqual(parsed["meta"]["turn"], "w")

    def test_rejects_wrong_field_count(self):
        parsed, errors = parse_fen("8/8/8/8/8/8/8/8 w - -")
        self.assertIsNone(parsed)
        self.assertTrue(any("6 space-separated fields" in e for e in errors))

    def test_rejects_bad_rank_expansion(self):
        parsed, errors = parse_fen("8/8/8/8/8/8/8/9 w - - 0 1")
        self.assertTrue(any("9" in e or "expands" in e for e in errors))
        self.assertIsNone(parsed)

    def test_ledger_roundtrip(self):
        grid, errors = parse_ledger("\n".join(START_ROWS))
        self.assertEqual(errors, [])
        self.assertEqual(ledger_to_fen(grid), START_FEN.split()[0])

    def test_fen_from_grid(self):
        grid, _ = parse_ledger("\n".join(START_ROWS))
        self.assertEqual(fen_from_grid(grid), START_FEN)


class ValidationTests(unittest.TestCase):
    def test_start_legal(self):
        v = validate_fen(START_FEN)
        self.assertTrue(v.legal, [e.message for e in v.errors])
        self.assertEqual(v.suspect_squares, [])

    def test_pawn_on_backrank(self):
        v = validate_fen("4k3/8/8/8/8/8/8/P3K3 w - - 0 1")
        self.assertFalse(v.legal)
        self.assertIn("a1", v.suspect_squares)
        self.assertTrue(any("pawn on a1" in e.message for e in v.errors))

    def test_adjacent_kings(self):
        v = validate_fen("8/8/8/8/8/8/4k3/4K3 w - - 0 1")
        self.assertFalse(v.legal)
        self.assertTrue(any(e.code == "adjacent-kings" for e in v.errors))
        self.assertEqual(set(v.suspect_squares), {"e1", "e2"})

    def test_castling_needs_rook(self):
        v = validate_fen("4k3/8/8/8/8/8/8/4K3 w K - 0 1")
        self.assertFalse(v.legal)
        self.assertTrue(any(e.code == "castling-material" for e in v.errors))

    def test_en_passant_square(self):
        good = validate_fen("4k3/8/8/4p3/8/8/8/4K3 w - e6 0 1")
        self.assertTrue(good.legal, [e.message for e in good.errors])
        bad = validate_fen("4k3/8/8/8/8/8/8/4K3 w - e6 0 1")
        self.assertFalse(bad.legal)
        self.assertTrue(any(e.code == "ep-pawn" for e in bad.errors))

    def test_side_not_to_move_in_check(self):
        v = validate_fen("4k3/8/8/8/8/8/8/4R1K1 w - - 0 1")
        self.assertFalse(v.legal)
        self.assertTrue(any(e.code == "opposite-check" for e in v.errors))

    def test_promotion_material(self):
        # Four bishops and eight pawns cannot be reached: only seven original
        # non-pawns exist and no pawn has gone missing to promote.
        bad = validate_fen("4k3/8/8/8/8/BB6/PPPPPPPP/RNBQKBNR w - - 0 1")
        self.assertFalse(bad.legal)
        self.assertTrue(any(e.code == "promotion-material" for e in bad.errors))
        # Six pawns and four bishops is possible via two promotions.
        good = validate_fen("4k3/8/8/8/8/8/BPPBPPPP/RNBQKBNR w - - 0 1")
        self.assertTrue(good.legal, [e.message for e in good.errors])

    def test_counts(self):
        grid, _ = parse_ledger("\n".join(START_ROWS))
        counts = grid_counts(grid)
        self.assertEqual(counts["white"]["total"], 16)
        self.assertEqual(counts["black"]["p"], 8)

    def test_builtin_validator_without_python_chess(self):
        with patch("chessdiagram.rules.chess", None):
            legal = validate_fen(START_FEN)
            self.assertTrue(legal.legal)
            self.assertEqual(legal.python_chess, "not installed")
            bad = validate_fen("8/8/8/8/8/8/4k3/4K3 w - - 0 1")
            self.assertFalse(bad.legal)
            self.assertTrue(any(e.code == "adjacent-kings" for e in bad.errors))
            opposite = validate_fen("4k3/8/8/8/8/8/8/4R1K1 w - - 0 1")
            self.assertFalse(opposite.legal)
            self.assertTrue(any(e.code == "opposite-check" for e in opposite.errors))

    def test_orientation_penalty_start_is_legal(self):
        # Piece placement alone cannot orient a symmetric position: the
        # mirrored start is also legal for the other side to move.  Orientation
        # must come from printed labels or OCR evidence.
        grid, _ = parse_ledger("\n".join(START_ROWS))
        self.assertEqual(orientation_penalty(grid)["penalty"], 0)

    def test_flipped_grid_is_involution(self):
        grid, _ = parse_ledger("\n".join(START_ROWS))
        self.assertEqual(flipped_grid(flipped_grid(grid)), grid)


if __name__ == "__main__":
    unittest.main()
