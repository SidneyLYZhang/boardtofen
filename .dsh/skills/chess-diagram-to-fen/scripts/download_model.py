#!/usr/bin/env python3
"""Download the 2d-chess-ocr ONNX weights into scripts/models/.

The default YOLO26-m model is about 82 MB.  Use --variant n for the 9.8 MB
fallback, or --copy <file> to install a model you already have (offline).

The weights are published by AndrewSpano/2d-chess-ocr under the MIT license.
See THIRD_PARTY_NOTICES.md and LICENSES/2d-chess-ocr-MIT.txt.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from chessdiagram.constants import (  # noqa: E402
    DEFAULT_MODEL_DIR, DEFAULT_VARIANT, MODEL_HF_URL, MODEL_REPO, MODEL_SPECS,
)
from chessdiagram.model_store import (  # noqa: E402
    ModelError, copy_model, download_variant,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", choices=["m", "n", "all"], default=DEFAULT_VARIANT,
                        help="which weights to download (default: m)")
    parser.add_argument("--dest", default=str(DEFAULT_MODEL_DIR),
                        help=f"model directory (default: {DEFAULT_MODEL_DIR})")
    parser.add_argument("--mirror", help="Hugging Face mirror, e.g. https://hf-mirror.com")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip the sha256 check (not recommended)")
    parser.add_argument("--copy", metavar="ONNX",
                        help="copy a local .onnx file instead of downloading")
    parser.add_argument("--list", action="store_true", help="show the model catalogue")
    args = parser.parse_args(argv)

    if args.list:
        print(f"{MODEL_REPO} - {MODEL_HF_URL}")
        for variant, spec in MODEL_SPECS.items():
            print(f"  {variant}: {spec['filename']}  "
                  f"{spec['size'] / 1e6:.1f} MB  sha256={spec['sha256'][:12]}...")
            print(f"     {spec['note']}")
        return 0

    dest = Path(args.dest)
    try:
        if args.copy:
            path = copy_model(args.copy, dest)
            print(f"copied: {path}")
            print("note: verify the file against the published hash before trusting it.")
            return 0
        variants = ["m", "n"] if args.variant == "all" else [args.variant]
        for variant in variants:
            print(f"== {variant} ==")
            path = download_variant(variant, dest, args.mirror, args.force,
                                    verify=not args.no_verify)
            print(f"ready: {path}")
    except (ModelError, OSError) as exc:
        print(f"MODEL ERROR: {exc}", file=sys.stderr)
        return 1
    print("\nNext: python scripts/selftest.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
