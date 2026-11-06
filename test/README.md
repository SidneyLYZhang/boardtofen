# Tests

Repository-level tests for the `chess-diagram-to-fen` skill. They live outside the
skill directory so the installed artifact stays small.

```bash
python test/run_tests.py
python test/run_tests.py -v
python test/run_tests.py test.test_rules
```

| File | Covers | Requirements |
|---|---|---|
| `test_rules.py` | FEN syntax, validation (with and without python-chess), promotion material, castling, en passant, orientation | Pillow, NumPy, optional python-chess |
| `test_geometry.py` | centre-to-square mapping, pass merging, label evidence, bbox refinement | Pillow, NumPy |
| `test_detector.py` | end-to-end xyxy and standard cxcywh ONNX decoding | NumPy |
| `test_imaging.py` | font fallback on Pillow < 10.1, RGBA compositing | Pillow |
| `test_pipeline.py` | review selection (`--review-conf`), staged-report guard | Pillow, NumPy |
| `test_ledger.py` | manual `fen` return code | Pillow, NumPy |
| `test_docs.py` | frontmatter, completion criteria, reference pointers, notices, requirements | none |
| `test_integration.py` | full `solve`, 180° orientation, `stage --bbox`, metadata on `read`, `apply` round-trip | ONNX Runtime + model |

The integration class prints `skipped` when `onnxruntime` or
`scripts/models/2d-chess-ocr/*.onnx` is missing. Install dependencies and fetch
the model first if you want that coverage:

```bash
python -m pip install -r .dsh/skills/chess-diagram-to-fen/requirements.txt
python .dsh/skills/chess-diagram-to-fen/scripts/download_model.py
```

Temporary files/directories are created under `test/` and removed by the tests.
No real diagram or network access is needed.
