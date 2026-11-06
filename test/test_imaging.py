"""Unit tests for image helpers that do not need the model."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

from chessdiagram.imaging import font, load_rgb


class FontTests(unittest.TestCase):
    def test_falls_back_when_truetype_is_missing(self):
        with patch("chessdiagram.imaging.ImageFont.truetype",
                   side_effect=OSError("no fonts")), \
                patch("chessdiagram.imaging.ImageFont.load_default",
                      side_effect=[TypeError("old Pillow"), "fallback"]):
            self.assertEqual(font(12), "fallback")


class LoadTests(unittest.TestCase):
    def test_rgba_is_composited_on_paper(self):
        import tempfile
        from pathlib import Path
        from test.helpers import ROOT

        with tempfile.TemporaryDirectory(dir=ROOT / "test") as tmp:
            path = Path(tmp) / "alpha.png"
            Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(path)
            loaded = load_rgb(path)
            self.assertEqual(loaded.mode, "RGB")
            self.assertEqual(loaded.size, (4, 4))


if __name__ == "__main__":
    unittest.main()
