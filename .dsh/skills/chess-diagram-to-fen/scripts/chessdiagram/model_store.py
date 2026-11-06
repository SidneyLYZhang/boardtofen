"""Locate, verify, and download the 2d-chess-ocr ONNX weights.

The weights live inside the skill at ``scripts/models/2d-chess-ocr/`` so the
recognition script is self-contained after the one-time download.  No model
file is bundled with the repository: model files are large and the download is
explicit (or automatic on first use).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .constants import (
    DEFAULT_MODEL_DIR, DEFAULT_VARIANT, MODEL_REPO, MODEL_SPECS, MODEL_HF_URL,
)

CHUNK = 1 << 20


class ModelError(RuntimeError):
    """The model is missing, corrupt, or could not be downloaded."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _mirror_url(url: str, mirror: str | None) -> str:
    if not mirror:
        return url
    mirror = mirror.rstrip("/")
    if url.startswith(MODEL_HF_URL):
        return mirror + url[len("https://huggingface.co"):]
    if url.startswith("https://huggingface.co"):
        return mirror + url[len("https://huggingface.co"):]
    return url


def _download(url: str, dest: Path, expected_size: int | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "chess-diagram-to-fen/2.0"})
            with urllib.request.urlopen(req, timeout=90) as response, part.open("wb") as fh:
                total = int(response.headers.get("Content-Length") or expected_size or 0)
                done = 0
                started = time.time()
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if total and sys.stderr.isatty():
                        pct = 100.0 * done / total
                        sys.stderr.write(
                            f"\r  downloading {dest.name}: {pct:5.1f}% "
                            f"({_human(done)} / {_human(total)})")
                        sys.stderr.flush()
                if sys.stderr.isatty():
                    sys.stderr.write("\n")
            if expected_size is not None and part.stat().st_size != expected_size:
                raise ModelError(
                    f"downloaded {part.stat().st_size} bytes, expected {expected_size}")
            part.replace(dest)
            return
        except Exception as exc:  # network, HTTP, size, disk
            last_error = exc
            part.unlink(missing_ok=True)
            if attempt < 3:
                wait = 2 ** (attempt - 1)
                print(f"  download failed ({exc}); retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise ModelError(
        f"could not download {url}: {last_error}. "
        "Check your network, or pass --mirror https://hf-mirror.com, "
        "or download the file manually into the model directory.")


def _write_info(dest_dir: Path, variant: str, path: Path) -> None:
    spec = MODEL_SPECS[variant]
    info = {
        "repo": MODEL_REPO,
        "repo_url": "https://github.com/AndrewSpano/2d-chess-ocr",
        "license": "MIT (project); ONNX metadata: AGPL-3.0 "
                   "(see THIRD_PARTY_NOTICES.md)",
        "variant": variant,
        "file": path.name,
        "size": path.stat().st_size,
        "sha256": spec["sha256"],
        "source": spec["url"],
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    (dest_dir / "MODEL_INFO.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8")


def download_variant(variant: str, dest_dir: str | Path | None = None,
                     mirror: str | None = None, force: bool = False,
                     verify: bool = True) -> Path:
    """Download one model variant into ``dest_dir`` and return its path."""
    if variant not in MODEL_SPECS:
        raise ModelError(f"unknown model variant {variant!r}; choose m or n")
    spec = MODEL_SPECS[variant]
    dest_dir = Path(dest_dir) if dest_dir else DEFAULT_MODEL_DIR
    dest = dest_dir / spec["filename"]
    if dest.exists() and not force:
        if dest.stat().st_size == spec["size"]:
            if not verify or _sha256(dest) == spec["sha256"]:
                _write_info(dest_dir, variant, dest)
                return dest
        print(f"  existing {dest.name} is incomplete or corrupt; re-downloading",
              file=sys.stderr)
        dest.unlink()
    url = _mirror_url(spec["url"], mirror)
    print(f"  model: {spec['note']}\n  source: {url}", file=sys.stderr)
    _download(url, dest, spec["size"])
    actual = _sha256(dest)
    if verify and actual != spec["sha256"]:
        dest.unlink(missing_ok=True)
        raise ModelError(
            f"sha256 mismatch for {dest.name}: got {actual}, expected {spec['sha256']}")
    _write_info(dest_dir, variant, dest)
    print(f"  saved: {dest} ({_human(dest.stat().st_size)})", file=sys.stderr)
    return dest


def available_variants(dest_dir: str | Path | None = None) -> dict[str, Path]:
    dest_dir = Path(dest_dir) if dest_dir else DEFAULT_MODEL_DIR
    found = {}
    for variant, spec in MODEL_SPECS.items():
        path = dest_dir / spec["filename"]
        if path.is_file() and path.stat().st_size > 0:
            found[variant] = path
    return found


def _verify(path: Path, variant: str, verify: bool) -> None:
    spec = MODEL_SPECS[variant]
    if not path.is_file():
        raise ModelError(f"model file not found: {path}")
    size = path.stat().st_size
    if size != spec["size"]:
        raise ModelError(
            f"{path.name} has {size} bytes, expected {spec['size']}; "
            f"delete it and run download_model.py")
    if verify and _sha256(path) != spec["sha256"]:
        raise ModelError(
            f"{path.name} failed its sha256 check; delete it and run download_model.py")


def ensure_model(variant: str = "auto", model_path: str | Path | None = None,
                 dest_dir: str | Path | None = None, allow_download: bool = True,
                 mirror: str | None = None, verify: bool = True) -> Path:
    """Return a verified model path, downloading it when necessary.

    ``variant='auto'`` prefers the accurate ``m`` weights, then ``n``, then
    downloads ``m``.  ``CHESS_OCR_MODEL_PATH`` overrides everything.
    """
    env_path = os.environ.get("CHESS_OCR_MODEL_PATH")
    if model_path is None and env_path:
        model_path = env_path
    if model_path:
        path = Path(model_path)
        if not path.is_file():
            raise ModelError(f"model file not found: {path}")
        # A user-supplied path is trusted for size only; its variant is unknown.
        if path.stat().st_size < 1_000_000:
            raise ModelError(f"{path} is too small to be a YOLO ONNX model")
        return path

    dest_dir = Path(dest_dir) if dest_dir else DEFAULT_MODEL_DIR
    mirror = mirror or os.environ.get("CHESS_OCR_MIRROR") or os.environ.get("HF_ENDPOINT")
    found = available_variants(dest_dir)

    if variant == "auto":
        for candidate in (DEFAULT_VARIANT, "n"):
            if candidate not in found:
                continue
            try:
                _verify(found[candidate], candidate, verify)
                return found[candidate]
            except ModelError:
                # A corrupt m should not hide a valid n.
                if candidate != "n" and "n" in found:
                    continue
                raise
        if not allow_download:
            raise ModelError(_missing_message(dest_dir))
        return download_variant(DEFAULT_VARIANT, dest_dir, mirror, verify=verify)

    if variant not in MODEL_SPECS:
        raise ModelError(f"unknown model variant {variant!r}; choose m or n")
    if variant in found:
        _verify(found[variant], variant, verify)
        return found[variant]
    if not allow_download:
        raise ModelError(_missing_message(dest_dir))
    return download_variant(variant, dest_dir, mirror, verify=verify)


def _missing_message(dest_dir: Path) -> str:
    names = ", ".join(spec["filename"] for spec in MODEL_SPECS.values())
    return (
        f"the 2d-chess-ocr model is not downloaded in {dest_dir} "
        f"(expected one of: {names}).\n"
        "Run: python scripts/download_model.py\n"
        "Then retry. The default YOLO26-m weights are about 82 MB and are "
        "downloaded once from Hugging Face.")


def copy_model(source: str | Path, dest_dir: str | Path | None = None) -> Path:
    """Copy a local ONNX file into the model directory (useful offline)."""
    dest_dir = Path(dest_dir) if dest_dir else DEFAULT_MODEL_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    source = Path(source)
    if not source.is_file():
        raise ModelError(f"source model not found: {source}")
    dest = dest_dir / source.name
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    return dest
