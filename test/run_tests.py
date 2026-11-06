#!/usr/bin/env python3
"""Run the chess-diagram-to-fen test suite with the standard library.

Usage:
    python test/run_tests.py
    python test/run_tests.py -v
    python test/run_tests.py test.test_rules

The integration tests skip themselves unless ONNX Runtime and the model are
present.  Unit tests need only Pillow, NumPy, and (optionally) python-chess.
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = ROOT / ".dsh" / "skills" / "chess-diagram-to-fen" / "scripts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tests", nargs="*", help="optional dotted test names")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    for path in (str(ROOT), str(SKILL_SCRIPTS)):
        if path not in sys.path:
            sys.path.insert(0, path)

    if args.tests:
        loader = unittest.TestLoader()
        suite = unittest.TestSuite(
            loader.loadTestsFromName(name) for name in args.tests)
    else:
        suite = unittest.defaultTestLoader.discover(
            str(ROOT / "test"), pattern="test_*.py", top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
