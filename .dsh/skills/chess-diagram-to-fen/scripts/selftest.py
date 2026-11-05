#!/usr/bin/env python3
"""Verify a chess-diagram-to-fen installation without a real diagram.

Renders the starting position, stages it through the same prepare/check/annotate
path used for a photographed board, and checks every expected artifact. No
network access and no files outside a temporary directory (unless --keep).

Run from the skill directory:  python scripts/selftest.py
Add --workdir <dir> when the current directory is not writable.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.dont_write_bytecode = True  # keep the installed skill directory clean

MIN_PYTHON = (3, 10)
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
REQUIRED_FILES = (
    "SKILL.md",
    "references/recognition.md",
    "references/verification.md",
    "scripts/boardtool.py",
)


def run_command(func, args) -> tuple[int, str]:
    """Run one boardtool command and capture its output."""
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        code = func(args)
    return code, out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="keep the temporary work directory")
    parser.add_argument("--json", action="store_true", help="print a JSON summary")
    parser.add_argument("--workdir", help="writable directory for temporary files (default: cwd)")
    args = parser.parse_args(argv)

    checks: list[dict] = []
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})
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
        check("dependencies", False, f"{exc}; install with python -m pip install -r requirements.txt")
        for name in REQUIRED_FILES:
            check(f"file {name}", (skill_dir / name).is_file(), str(skill_dir / name))
        print_summary(checks, failures, args.json, None)
        return 1

    try:
        import chess
        check("python-chess", True, f"{chess.__version__} (optional)")
    except ImportError:
        check("python-chess", True, "not installed (optional)")

    for name in REQUIRED_FILES:
        path = skill_dir / name
        check(f"file {name}", path.is_file(), str(path))

    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8") if (skill_dir / "SKILL.md").is_file() else ""
    skill_md = skill_md.lstrip("\ufeff").replace("\r\n", "\n")
    check("frontmatter", skill_md.startswith("---\n") and "\nname: chess-diagram-to-fen" in skill_md
          and "\ndescription:" in skill_md, "SKILL.md needs YAML name + description")

    if failures:
        print_summary(checks, failures, args.json, None)
        return 1

    sys.path.insert(0, str(skill_dir / "scripts"))
    import boardtool  # noqa: E402  (path setup must precede the import)

    base = Path(args.workdir).resolve() if args.workdir else Path.cwd()
    try:
        work_root = Path(tempfile.mkdtemp(prefix=".boardtofen-selftest-", dir=base))
    except OSError as exc:
        print(f"FAIL: cannot create a temporary directory in {base}: {exc}", file=sys.stderr)
        print("Hint: pass --workdir <writable directory>.", file=sys.stderr)
        return 1
    try:
        board_png = work_root / "board.png"
        work = work_root / "work"

        code, output = run_command(boardtool.cmd_render, argparse.Namespace(fen=START_FEN, out=str(board_png)))
        check("render", code == 0 and board_png.is_file() and board_png.stat().st_size > 10_000,
              f"exit {code}; {board_png.stat().st_size if board_png.exists() else 0} bytes")

        code, output = run_command(boardtool.cmd_prepare, argparse.Namespace(
            image=str(board_png), out=str(work), bbox=None, flip=False,
            no_deskew=False, grid_step=50))
        board_json = work / "board.json"
        data = json.loads(board_json.read_text(encoding="utf-8")) if board_json.is_file() else {}
        lines_x, lines_y = data.get("lines_x", []), data.get("lines_y", [])
        check("prepare", code == 0 and len(lines_x) == 9 and len(lines_y) == 9,
              f"exit {code}; {len(lines_x)}x{len(lines_y)} grid lines")
        for name in ("overlay.png", "contact.png", "q1.png", "q2.png", "q3.png", "q4.png",
                     "half_top.png", "half_bottom.png"):
            check(f"stage {name}", (work / name).is_file(), str(work / name))

        code, output = run_command(boardtool.cmd_check, argparse.Namespace(fen=START_FEN, json=False))
        check("check", code == 0 and "ARBITER: PASS" in output, f"exit {code}")

        audit = work / "audit.png"
        code, output = run_command(boardtool.cmd_annotate, argparse.Namespace(
            board=str(board_json), fen=START_FEN, out=str(audit), image=None))
        check("annotate", code == 0 and audit.is_file() and audit.stat().st_size > 10_000,
              f"exit {code}; {audit.stat().st_size if audit.exists() else 0} bytes")

        print_summary(checks, failures, args.json, work_root if args.keep else None)
    except Exception:
        failures.append(traceback.format_exc())
        print_summary(checks, failures, args.json, work_root if args.keep else None)
    finally:
        if not args.keep:
            import shutil
            shutil.rmtree(work_root, ignore_errors=True)

    return 1 if failures else 0


def print_summary(checks: list[dict], failures: list[str], as_json: bool, kept: Path | None) -> None:
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
        print("\nPASS: toolchain and the full diagram pipeline work.")
        print("Next: open a real diagram and ask the agent to convert it to FEN.")
    if kept:
        print(f"Work directory kept at: {kept}")


if __name__ == "__main__":
    sys.exit(main())
