"""Unit tests for the ONNX output decoders (no ONNX Runtime required)."""
from __future__ import annotations

import unittest

import numpy as np

from chessdiagram.detector import Detector


def _detector() -> Detector:
    det = Detector.__new__(Detector)
    det.iou = 0.5
    return det


class DecodeTests(unittest.TestCase):
    def test_end_to_end_xyxy(self):
        output = np.array([[[100, 120, 140, 160, 0.9, 7],
                            [200, 220, 240, 260, 0.2, 7]]], dtype=np.float32)
        dets = _detector()._decode(output, (640, 640), 1.0, 0, 0, 0.25)
        self.assertEqual(len(dets), 1)
        self.assertEqual(dets[0].name, "white_pawn")
        self.assertEqual(dets[0].xyxy, (100.0, 120.0, 140.0, 160.0))

    def test_standard_cxcywh(self):
        output = np.zeros((1, 20, 2), dtype=np.float32)
        output[0, :4, 0] = [100, 120, 40, 40]
        output[0, 4 + 7, 0] = 0.9       # white_pawn
        output[0, :4, 1] = [300, 320, 20, 20]
        output[0, 4 + 1, 1] = 0.8       # black_pawn
        dets = _detector()._decode(output, (640, 640), 1.0, 0, 0, 0.25)
        by_name = {d.name: d for d in dets}
        self.assertIn("white_pawn", by_name)
        self.assertIn("black_pawn", by_name)
        self.assertEqual(by_name["white_pawn"].xyxy, (80.0, 100.0, 120.0, 140.0))
        self.assertEqual(by_name["black_pawn"].xyxy, (290.0, 310.0, 310.0, 330.0))

    def test_letterbox_mapping(self):
        output = np.array([[[320, 320, 340, 340, 0.9, 7]]], dtype=np.float32)
        # 640 letterbox into 320 with 160 px of padding: one input pixel is two
        # output pixels, and the pad is removed before mapping.
        dets = _detector()._decode(output, (1000, 1000), 0.5, 160, 160, 0.25)
        self.assertEqual(dets[0].xyxy, (320.0, 320.0, 360.0, 360.0))


if __name__ == "__main__":
    unittest.main()
