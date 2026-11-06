"""Unit tests for detection-to-square mapping, merging, and orientation labels."""
from __future__ import annotations

import unittest

from test.helpers import START_ROWS, board_detections, mapping_with

from chessdiagram.detector import Detection
from chessdiagram.geometry import (
    evidence_from_pass, grid_from_cells, label_evidence, map_pass, merge_passes,
    refine_bbox_from_pieces,
)


class MapPassTests(unittest.TestCase):
    def setUp(self):
        self.dets = board_detections(START_ROWS)
        self.mapping = map_pass(self.dets, (0, 0), 800, 800, "test")

    def test_pieces_land_on_expected_squares(self):
        self.assertEqual(self.mapping["a8"][0].fen, "r")
        self.assertEqual(self.mapping["e8"][0].fen, "k")
        self.assertEqual(self.mapping["e1"][0].fen, "K")
        self.assertEqual(self.mapping["h1"][0].fen, "R")

    def test_empty_square_has_no_candidate(self):
        self.assertEqual(self.mapping["e4"], [])

    def test_centre_decides_boundary_piece(self):
        # A box centred on the d4/e4 boundary resolves to d4; the box corners
        # spilling into e4 do not steal the square.
        det = Detection(7, "white_pawn", 0.9, (290, 390, 410, 410))
        mapping = map_pass([det], (0, 0), 800, 800, "test")
        self.assertEqual(mapping["d4"][0].fen, "P")
        self.assertEqual(mapping["e4"], [])

    def test_evidence_summary(self):
        ev = evidence_from_pass(self.mapping)
        self.assertEqual(ev["count"], 32)
        self.assertGreater(ev["weight"], 10)


class MergeTests(unittest.TestCase):
    def test_agreement_keeps_confidence(self):
        cells = merge_passes([
            ("a", mapping_with("e4", [("P", 0.8)])),
            ("b", mapping_with("e4", [("P", 0.7)])),
        ])
        e4 = next(c for c in cells if c.square == "e4")
        self.assertEqual(e4.fen, "P")
        self.assertAlmostEqual(e4.confidence, 0.8)
        self.assertNotIn("pass-disagreement", e4.flags)

    def test_disagreement_keeps_alternative(self):
        cells = merge_passes([
            ("a", mapping_with("e4", [("P", 0.8)])),
            ("b", mapping_with("e4", [("p", 0.7)])),
        ])
        e4 = next(c for c in cells if c.square == "e4")
        self.assertEqual(e4.fen, "P")
        self.assertIn("pass-disagreement", e4.flags)
        self.assertEqual([c.fen for c in e4.alternatives], ["p"])

    def test_single_pass_is_flagged(self):
        cells = merge_passes([("a", mapping_with("e4", [("P", 0.8)]))],
                             review_conf=0.75)
        e4 = next(c for c in cells if c.square == "e4")
        self.assertIn("single-pass", e4.flags)
        self.assertAlmostEqual(e4.confidence, 0.8 * 0.85)

    def test_grid_from_cells(self):
        cells = merge_passes([("a", mapping_with("e4", [("P", 0.8)]))])
        grid = grid_from_cells(cells)
        self.assertEqual(grid[4][4], "P")
        self.assertEqual(grid[0][0], ".")


class LabelTests(unittest.TestCase):
    def test_label_at_bottom_is_normal(self):
        det = Detection(13, "rank_one_id", 0.9, (0, 760, 10, 770))
        ev = label_evidence([det], (0, 0, 800, 800))
        self.assertEqual(ev["vote"], "normal")

    def test_label_at_top_is_flipped(self):
        det = Detection(13, "rank_one_id", 0.9, (0, 30, 10, 40))
        ev = label_evidence([det], (0, 0, 800, 800))
        self.assertEqual(ev["vote"], "flipped")

    def test_diagram_number_above_board_is_ignored(self):
        det = Detection(13, "rank_one_id", 0.9, (20, -40, 30, -30))
        ev = label_evidence([det], (0, 0, 800, 800))
        self.assertEqual(ev["vote"], "none")

    def test_label_inside_board_centre_is_ignored(self):
        det = Detection(13, "rank_one_id", 0.9, (400, 30, 410, 40))
        ev = label_evidence([det], (0, 0, 800, 800))
        self.assertEqual(ev["vote"], "none")


class RefineTests(unittest.TestCase):
    def test_piece_lattice_refines_offset_box(self):
        dets = board_detections(START_ROWS)
        bbox, evidence = refine_bbox_from_pieces((10, 10, 790, 790), dets)
        self.assertTrue(evidence["applied"], evidence)
        self.assertAlmostEqual(bbox[0], 0, delta=2)
        self.assertAlmostEqual(bbox[1], 0, delta=2)
        self.assertAlmostEqual(bbox[2], 800, delta=2)
        self.assertAlmostEqual(bbox[3], 800, delta=2)

    def test_sparse_board_keeps_box(self):
        dets = board_detections([
            "........",
            "........",
            "........",
            "........",
            "........",
            "........",
            "........",
            "....K..k",
        ])
        bbox, evidence = refine_bbox_from_pieces((10, 10, 790, 790), dets)
        self.assertFalse(evidence["applied"])
        self.assertEqual(bbox, (10, 10, 790, 790))


if __name__ == "__main__":
    unittest.main()
