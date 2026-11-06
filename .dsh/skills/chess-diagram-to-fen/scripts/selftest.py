#!/usr/bin/env python3
"""Verify a chess-diagram-to-fen installation end to end.

The test renders the starting position, runs the full model pipeline on four
variants (normal, 180-degree rotated, no coordinate labels, rotated without
labels), applies a manual correction, and checks the validator.  It needs the
2d-chess-ocr ONNX weights; run ``python scripts/download_model.py`` first.

Run from the skill directory:  python scripts/selftest.py
Add --workdir <dir> when the current directory is not writable.
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import tempfile
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # reported by the dependency check below
    Image = None  # type: ignore[assignment]

sys.dont_write_bytecode = True  # keep the installed skill directory clean

MIN_PYTHON = (3, 10)
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"
REQUIRED_FILES = (
    "SKILL.md",
    "requirements.txt",
    "THIRD_PARTY_NOTICES.md",
    "LICENSES/2d-chess-ocr-MIT.txt",
    "references/recognition.md",
    "references/verification.md",
    "references/ocr.md",
    "scripts/boardtool.py",
    "scripts/download_model.py",
    "scripts/selftest.py",
    "scripts/chessdiagram/__init__.py",
    "scripts/chessdiagram/constants.py",
    "scripts/chessdiagram/imaging.py",
    "scripts/chessdiagram/model_store.py",
    "scripts/chessdiagram/detector.py",
    "scripts/chessdiagram/geometry.py",
    "scripts/chessdiagram/rules.py",
    "scripts/chessdiagram/artifacts.py",
    "scripts/chessdiagram/pipeline.py",
    "scripts/chessdiagram/ledger.py",
)


def run_command(func, args) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        code = func(args)
    return code, out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="keep the temporary work directory")
    parser.add_argument("--json", action="store_true", help="print a JSON summary")
    parser.add_argument("--workdir", help="writable directory for temporary files (default: cwd)")
    parser.add_argument("--download-model", action="store_true",
                        help="download the ONNX weights if they are missing")
    parser.add_argument("--variant", choices=["auto", "m", "n"], default="auto")
    args = parser.parse_args(argv)

    checks: list[dict] = []
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(f"{name}: {detail}" if detail else name)

    skill_dir = Path(__file__).resolve().parents[1]

    check("python", sys.version_info >= MIN_PYTHON,
          f"{sys.version.split()[0]} (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)")

    try:
        import numpy
        import PIL
        check("Pillow", True, PIL.__version__)
        check("numpy", True, numpy.__version__)
    except ImportError as exc:
        check("dependencies", False,
              f"{exc}; install with python -m pip install -r requirements.txt")
        for name in REQUIRED_FILES:
            check(f"file {name}", (skill_dir / name).is_file(), str(skill_dir / name))
        print_summary(checks, failures, args.json, None)
        return 1

    try:
        import onnxruntime
        check("onnxruntime", True, onnxruntime.__version__)
    except ImportError as exc:
        check("onnxruntime", False,
              f"{exc}; install with python -m pip install -r requirements.txt")

    try:
        import chess
        check("python-chess (optional)", True, f"{chess.__version__}; GPL-3.0")
    except ImportError:
        check("python-chess (optional)", True,
              "not installed; built-in checks only "
              "(install python-chess for GPL-3.0 extra checks)")

    for name in REQUIRED_FILES:
        path = skill_dir / name
        check(f"file {name}", path.is_file(), str(path))

    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8") \
        if (skill_dir / "SKILL.md").is_file() else ""
    skill_md = skill_md.lstrip("\ufeff").replace("\r\n", "\n")
    check("frontmatter",
          skill_md.startswith("---\n")
          and "\nname: chess-diagram-to-fen" in skill_md
          and "\ndescription:" in skill_md
          and "\nlicense:" in skill_md,
          "" if skill_md.startswith("---\n") else
          "SKILL.md needs YAML name + description + license")

    if failures:
        print_summary(checks, failures, args.json, None)
        return 1

    sys.path.insert(0, str(skill_dir / "scripts"))
    import boardtool  # noqa: E402
    from chessdiagram.imaging import load_rgb  # noqa: E402
    from chessdiagram.ledger import cmd_render  # noqa: E402
    from chessdiagram.model_store import ensure_model  # noqa: E402
    from chessdiagram.pipeline import (  # noqa: E402
        SolveOptions, apply_changes, review_sheet, solve, stage,
    )
    from chessdiagram.rules import validate_fen  # noqa: E402

    try:
        model = ensure_model(variant=args.variant,
                             allow_download=args.download_model)
        check("model", True, str(model))
    except Exception as exc:  # noqa: BLE001 - any model failure is a FAIL
        check("model", False, str(exc))
        print_summary(checks, failures, args.json, None)
        return 1

    base = Path(args.workdir).resolve() if args.workdir else Path.cwd()
    try:
        work_root = Path(tempfile.mkdtemp(prefix=".boardtofen-selftest-", dir=base))
    except OSError as exc:
        print(f"FAIL: cannot create a temporary directory in {base}: {exc}", file=sys.stderr)
        print("Hint: pass --workdir <writable directory>.", file=sys.stderr)
        return 1

    def options(image: Path, out: Path) -> SolveOptions:
        return SolveOptions(
            image=str(image), out=str(out), model=str(model), variant=args.variant,
            allow_download=False, review_conf=0.75, deskew=True)

    try:
        start_png = work_root / "start.png"
        code, output = run_command(cmd_render,
                                   argparse.Namespace(fen=START_FEN, out=str(start_png)))
        check("render", code == 0 and start_png.is_file()
              and start_png.stat().st_size > 10_000,
              f"exit {code}; {start_png.stat().st_size if start_png.exists() else 0} bytes")

        work = work_root / "start-work"
        report = solve(options(start_png, work))
        check("solve normal", report.get("ok") and report.get("fen") == START_FEN,
              report.get("summary", "")[:400])
        check("orientation normal", report.get("board", {}).get("orientation") == "white",
              str(report.get("board", {}).get("orientation_source")))
        check("cells 64", len(report.get("cells", {})) == 64,
              str(len(report.get("cells", {}))))
        check("validation pass", report.get("validation", {}).get("legal") is True,
              json.dumps(report.get("validation", {}).get("errors", []))[:400])
        artifacts = report.get("artifacts", {})
        for key in ("audit", "cells", "cells_json", "cells_sheet", "report", "overlay"):
            check(f"artifact {key}", bool(artifacts.get(key))
                  and Path(artifacts[key]).exists(), str(artifacts.get(key)))

        # Black at the bottom, with printed labels.
        rotated = work_root / "start-rotated.png"
        load_rgb(start_png).transpose(Image.Transpose.ROTATE_180).save(rotated)
        report_rot = solve(options(rotated, work_root / "rot-work"))
        check("solve rotated", report_rot.get("ok") and report_rot.get("fen") == START_FEN,
              report_rot.get("summary", "")[:400])
        check("orientation rotated",
              report_rot.get("board", {}).get("orientation") == "black",
              str(report_rot.get("board", {}).get("orientation_source")))

        # No printed coordinates: orientation must come from the model + rules.
        no_label = work_root / "start-no-labels.png"
        load_rgb(start_png).crop((60, 60, 860, 860)).save(no_label)
        report_nl = solve(options(no_label, work_root / "nolabel-work"))
        check("solve no labels", report_nl.get("ok") and report_nl.get("fen") == START_FEN,
              report_nl.get("summary", "")[:400])
        check("orientation no labels",
              report_nl.get("board", {}).get("orientation") == "white",
              str(report_nl.get("board", {}).get("orientation_source")))

        no_label_rot = work_root / "start-no-labels-rotated.png"
        load_rgb(no_label).transpose(Image.Transpose.ROTATE_180).save(no_label_rot)
        report_nlr = solve(options(no_label_rot, work_root / "nolabel-rot-work"))
        check("solve no labels rotated",
              report_nlr.get("ok") and report_nlr.get("fen") == START_FEN,
              report_nlr.get("summary", "")[:400])
        check("orientation no labels rotated",
              report_nlr.get("board", {}).get("orientation") == "black",
              str(report_nlr.get("board", {}).get("orientation_source")))

        # Manual correction: remove a pawn, then restore it.
        board_json = work / "board.json"
        corrected = apply_changes(board_json, {"e2": "."}, "selftest")
        check("apply correction", "PPPP1PPP" in (corrected.get("fen") or ""),
              str(corrected.get("fen")))
        restored = apply_changes(board_json, {"e2": "P"}, "selftest restore")
        check("apply restore", restored.get("fen") == START_FEN, str(restored.get("fen")))

        # Review sheet for one square.
        review = review_sheet(board_json, ["e2"], work / "review-selftest.png")
        check("review", review.get("ok") and Path(review["review"]).is_file(),
              str(review.get("review")))

        # Staging without OCR.
        staged = stage(options(start_png, work_root / "stage-work"))
        check("stage", staged.get("ok") and len(staged.get("cells", {})) == 64,
              staged.get("summary", "")[:300])

        # Validator: a pawn cannot stand on rank 1.
        bad = validate_fen("4k3/8/8/8/8/8/8/P3K3 w - - 0 1")
        check("validator rejects illegal", bad.legal is False,
              "; ".join(e.message for e in bad.errors))
        code, out = run_command(boardtool.cmd_check, argparse.Namespace(
            fen="4k3/8/8/8/8/8/8/P3K3 w - - 0 1", json=False))
        check("check exit code", code == 1 and "ARBITER: FAIL" in out, f"exit {code}")

        print_summary(checks, failures, args.json, work_root if args.keep else None)
    except Exception:
        failures.append(traceback.format_exc())
        print_summary(checks, failures, args.json, work_root if args.keep else None)
    finally:
        if not args.keep:
            shutil.rmtree(work_root, ignore_errors=True)

    return 1 if failures else 0


def print_summary(checks: list[dict], failures: list[str], as_json: bool,
                  kept: Path | None) -> None:
    if as_json:
        print(json.dumps({"ok": not failures, "checks": checks, "failures": failures,
                          "workdir": str(kept) if kept else None}, indent=2))
        return
    width = max((len(c["check"]) for c in checks), default=0)
    for item in checks:
        status = "OK  " if item["ok"] else "FAIL"
        detail = f"  {item['detail']}" if item["detail"] else ""
        print(f"  {status} {item['check']:<{width}}{detail}")
    if failures:
        print("\nFAIL: the installation is not complete.")
        for failure in failures:
            print(f"  {failure}")
        print("\nFix the items above, then rerun: python scripts/selftest.py")
    else:
        print("\nPASS: model, board detection, orientation, OCR, FEN, and audit work.")
        print("Next: open a real diagram and ask the agent to convert it to FEN.")
    if kept:
        print(f"Work directory kept at: {kept}")


if __name__ == "__main__":
    sys.exit(main())
