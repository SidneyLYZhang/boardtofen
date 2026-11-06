# Manual fallback

Use this only when the 2d-chess-ocr model cannot run: no network and no local
ONNX file, an unsupported piece set, or a diagram the detector refuses. The
normal `solve` path is faster and far less error-prone.

## 1 — Stage the board and cells

```bash
python scripts/boardtool.py stage board.png --out work
```

`stage` tries the model for board detection and falls back to classical CV. It
writes `board.png`, `overlay.png`, `cells/`, `cells.png`, `cells.json`, and
`board.json`. Inspect `overlay.png`; if the box is wrong, rerun with
`--bbox x0,y0,x1,y1` around the board's **outer grid lines**.

## 2 — First read: quadrant sweep

Write `work/read1.txt` with 8 rows, rank 8 first, 8 FEN characters per row
(`KQRBNP` White, `kqrbnp` Black, `.` empty). Read `cells.png` quadrant by
quadrant, or open individual `cells/<square>.png` files. Use
`references/recognition.md` for silhouette and letter cues.

```bash
python scripts/boardtool.py inspect --board work/board.json \
  --squares e4,e5,f6 --out work/inspect.png
```

`inspect` zooms arbitrary squares with context. Then:

```bash
python scripts/boardtool.py counts work/read1.txt
```

**Done when** `read1.txt` is 8×8 and `counts` says `LEDGER: structurally OK`.

## 3 — Blind second read

Write `work/read2.txt` from the image alone, without opening `read1.txt`. Read a
different order: bottom half first, or file by file. Then:

```bash
python scripts/boardtool.py compare work/read1.txt work/read2.txt
```

**Done when** both reads exist and every difference is listed by `compare`.

## 4 — Adjudicate

For each differing square, inspect it, decide by silhouette first and context
second, and record the cue in `work/notes.md`. Write the resolved board to
`work/final.txt`, then confirm both comparisons are explained:

```bash
python scripts/boardtool.py compare work/read1.txt work/final.txt
python scripts/boardtool.py compare work/read2.txt work/final.txt
```

Do not pick the more plausible piece; ask the user or get a fresh read.

## 5 — Encode and audit

```bash
python scripts/boardtool.py fen --ledger work/final.txt
python scripts/boardtool.py check "<FEN>"
python scripts/boardtool.py annotate --board work/board.json \
  --fen "<FEN>" --out work/audit.png
```

`check` prints the ASCII board and the arbiter verdict. `annotate` stamps the FEN
onto `board.png`; scan all 64 labels. `work/final.txt` is the source of truth:
fix it there, rebuild the FEN, and regenerate the audit rather than patching the
FEN string.

**Done when** the audit labels match every printed piece and `ARBITER: PASS`, or
the position is reported as printed-illegal with the arbiter's errors.

## References

- `references/recognition.md` — piece silhouettes, lettered alphabets, printed
  artifacts, and ambiguity rules.
- `references/verification.md` — the six FEN fields, arbiter failures, and the
  audit checklist.
