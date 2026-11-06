# Third-party notices and acknowledgements

This skill is a pipeline around an external chess-board OCR model. The model
files are not bundled in the repository; `scripts/download_model.py` fetches
them into `scripts/models/2d-chess-ocr/`.

## 2d-chess-ocr — recognition model and postprocessing reference

- Project: **2d-chess-ocr** — “Extract FEN positions from images of 2D chessboards.”
- Author: **Andreas Spanopoulos** (GitHub: [AndrewSpano](https://github.com/AndrewSpano))
- Source: <https://github.com/AndrewSpano/2d-chess-ocr>
- Model weights: <https://huggingface.co/AndrewSpano/2d-chess-ocr>
- Project license: **MIT** (see [`LICENSES/2d-chess-ocr-MIT.txt`](LICENSES/2d-chess-ocr-MIT.txt))
- ONNX metadata: **AGPL-3.0** (see the warning below)

Copyright (c) 2026 Andreas Spanopoulos.

The skill uses the published ONNX export (`yolo26m-finetuned.onnx`, with the
smaller `yolo26n-finetuned.onnx` as a fallback), its 16-class label definition
(`chessboard`, twelve piece classes, `rank_one_id`, and two last-move tile
classes), and a re-implementation of its centre-to-square assignment and
orientation-marker logic. The postprocessing was rewritten for this skill so it
could be combined with a second inference pass, chess-rule scoring, and a
python-chess audit; it is not a line-for-line copy.

The 2d-chess-ocr project was trained with **Ultralytics YOLO26**. The repository
and Hugging Face model entry declare MIT, but the ONNX file's embedded metadata
says, verbatim:

```text
author: Ultralytics
version: 8.4.56
license: AGPL-3.0 License (https://ultralytics.com/license)
description: Ultralytics YOLO26m model fine-tuned for 2D chessboard OCR.
```

That is a genuine licensing ambiguity: a downstream user cannot rely on the
"MIT" label alone. This skill does **not** bundle or import Ultralytics code; it
runs the exported ONNX graph through ONNX Runtime. It also does not redistribute
the weights — `download_model.py` fetches them at install time. If you
redistribute the weights, build a commercial product, or need a definitive
answer, review both the 2d-chess-ocr repository and Ultralytics' AGPL/commercial
terms (or ask the model author) before relying on the MIT label.

If you use this skill in research or a product, please cite/acknowledge the
2d-chess-ocr project and its author.

## Runtime libraries

| Library | License | Role |
|---|---|---|
| [ONNX Runtime](https://onnxruntime.ai/) | MIT | Executes the exported detector on CPU or GPU |
| [Pillow](https://python-pillow.org/) | HPND | Image loading, cropping, and audit rendering |
| [NumPy](https://numpy.org/) | BSD-3-Clause | Array math and grid fitting |
| [python-chess](https://python-chess.readthedocs.io/) | **GPL-3.0** | Optional deepest legality checks; **not bundled** |

`python-chess` is optional. The skill ships its own structural validator
(kings, pawn ranks, counts, promotion material, checks, castling/en-passant
consistency) and uses python-chess, when installed, for attack analysis and a
second opinion. Because python-chess is GPL-3.0, it is listed in
`requirements.txt` only as an optional extra; install it if your use allows
GPL-3.0, or rely on the built-in checks.

## Other references

- The FEN standard (Forsyth–Edwards Notation) is described in the PGN standard:
  <https://www.saremba.de/chessgml/standards/pgn/pgn-complete.htm>
- The Agent Skills format: <https://agentskills.io/specification>
