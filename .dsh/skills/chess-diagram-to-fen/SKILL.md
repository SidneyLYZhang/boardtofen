---
name: chess-diagram-to-fen
description: "Chess diagram to FEN: convert a printed or on-screen 2D board image, or check an existing FEN against it."
compatibility: "Python 3.10+ with Pillow, NumPy, and ONNX Runtime; python-chess optional (GPL-3.0). Model downloaded explicitly into scripts/models/."
license: "MIT (software) / CC0-1.0 (documentation)"
---

# Chess diagram → FEN

A diagram gives 64 facts and no history. This skill uses the **2d-chess-ocr**
detector to read the board, splits it into 64 cells, assembles the FEN, and
validates it with chess rules. The model is not infallible: your job is to audit
its labels against the image, correct the few flagged or visibly wrong squares,
and report the FEN with an honest provenance table.

The sequence is: **board → orientation → cells → OCR → FEN → rules → audit**.
Do not skip the audit; legality is not truth.

Run commands from this skill's directory, or prefix `scripts/boardtool.py` with
its absolute path.

## Step 0 — Install and fetch the model

```bash
python -m pip install -r requirements.txt          # Pillow, NumPy, ONNX Runtime
python -m pip install python-chess                 # optional, GPL-3.0: extra checks
python scripts/download_model.py                   # ~82 MB, once
python scripts/selftest.py                         # must print PASS
```

The model is stored inside the skill at
`scripts/models/2d-chess-ocr/yolo26m-finetuned.onnx`. Download it explicitly
with `download_model.py`, or pass `--download` to `solve`/`stage`/`read` to
allow that one command to fetch it. Recognition never starts an implicit
download. Offline, use `download_model.py --copy <file>`. See
`references/ocr.md` and `THIRD_PARTY_NOTICES.md`.

**Done when** `selftest.py` prints `PASS` and the model file exists under
`scripts/models/2d-chess-ocr/`.

## Step 1 — Solve the diagram

```bash
python scripts/boardtool.py solve board.png --out work
```

This one command:

1. finds every 8×8 board (model; overlapping tiles and classical CV as fallbacks);
2. crops the selected board and snaps its box to the lattice of detected piece
   centres;
3. chooses the orientation:
   - a printed rank-1 label at the bottom → White at bottom;
   - at the top → Black at bottom (the crop is rotated 180° for FEN);
   - both orientations are also read; a conflict is reported as a warning but
     the printed label is kept, so `--orientation` remains the override;
   - no labels → piece evidence + chess rules decide;
   - if both are equally good → White at bottom (book convention);
4. splits the normalized board into 64 cells, rank 8 first, file a first;
5. runs the model at two context margins, reconciles the two reads per square;
6. assembles the FEN with the defaults `w - - 0 1`;
7. validates with the built-in rules and python-chess (when installed);
8. writes the audit images and a machine-readable report.

Useful options:

| Option | When |
|---|---|
| `--board-index N` | a page has several boards; choose the 0-based one in reading order |
| `--bbox x0,y0,x1,y1` | the board is not detected; box its **outer grid lines** |
| `--orientation white\|black`, `--flip` | override the orientation (recorded as `user`) |
| `--conf 0.25` | detector floor; lower for tiny pieces, raise for noisy scans |
| `--review-conf 0.75` | confidence below which a square is flagged for review |
| `--no-deskew` | the page is already axis-aligned |
| `--variant n` | use the 9.8 MB fallback model (weaker on book scans) |
| `--download` | allow this one run to fetch a missing model (no implicit network) |
| `--turn`, `--castling`, `--ep`, `--halfmove`, `--fullmove` | only when the page states these fields |

**Done when** the command prints a `FEN` line, the report has 64 cells, and the
`CHECK`/`FILES` lines show the arbiter verdict and the audit set: `audit.png`,
`review.png` (if any), `cells.png`, `cells/`, `cells.json`, and `report.json`.

## Step 2 — Audit all 64 squares

Open `work/audit.png` and the four `work/audit_q1.png` … `audit_q4.png` (larger,
easier to read). For every square, check that the tag matches the printed piece:

- red uppercase letter = White piece of that type;
- blue lowercase letter = Black piece of that type;
- dot = empty square;
- orange border = the model itself flagged the square for review.

A tag on the wrong square, on the wrong colour, or on emptiness is a mismatch.
Also check the empty squares: a piece under a dot is a miss. Pay special
attention to rank 1 and rank 8, and to cells where two similar silhouettes
(bishop/pawn, queen/king) are adjacent.

This full-board audit is mandatory. The model can be confidently wrong; the
review sheet alone does not cover every square. A legal FEN can still be wrong.

**Done when** every tag in all four quadrant audits sits on the piece it names,
or every mismatch is recorded in `work/notes.md` with the square and the cue.

## Step 3 — Inspect the flagged cells

If the report names review squares, open `work/review.png`. Each tile shows the
target square in a 3×3 context, the model's choice, its confidence, the
alternative class, and the flags. Decide from the **silhouette**, then context;
open `references/recognition.md` when the piece set is unfamiliar or lettered.

Typical flags:

- `pass-disagreement` — two reads chose different symbols; both are shown.
- `single-pass` — only one read saw a piece; the other missed it.
- `close-alternative` — a second class is within 0.12 confidence.
- `low-confidence` — below `--review-conf`.

For a square that is still unclear, use a bigger crop:

```bash
python scripts/boardtool.py inspect --board work/board.json \
  --squares e4,e5,f6 --out work/disputes.png
```

Record in `work/notes.md`: the square, the model's choice, the alternative, your
decision, and the cue (silhouette, base, cross, mitre, colour). If a square
survives inspection, ask the user or get a fresh read; do not pick the more
plausible piece.

**Done when** every review square has a decision in `notes.md`: confirmed,
corrected, or explicitly unresolved.

## Step 4 — Correct and re-check

Only after the visual audit, apply the differences:

```bash
python scripts/boardtool.py apply --board work/board.json \
  --set "e2=P,d2=P,a2=P" --note "audit: pawns on rank 2"
```

`apply` updates the cells (source `manual`), rebuilds the FEN, revalidates, and
regenerates the audit, review, and cell views. Use `.` for an empty square. Do
not patch the FEN string directly; the cells are the single source of truth.

**Done when** a fresh `audit.png` shows every tag on the correct piece and the
report's `review_squares` are either resolved or explicitly explained.

## Step 5 — Arbitrate

```bash
python scripts/boardtool.py check "<FEN>"
```

`check` prints the ASCII board, counts, metadata, python-chess's verdict (when
installed), and square-level errors. `ARBITER: PASS` means the position is legal,
not that it matches the image. If it fails:

- treat each error as a pointer to squares to re-read;
- do not move a piece merely to make the position legal;
- if the printed diagram is genuinely illegal (a composition or a puzzle), report
  it as printed and show the errors.

`python-chess` is optional because it is GPL-3.0; the built-in validator always
runs and covers kings, pawn ranks, counts, promotion material, checks, castling,
and en passant. Open `references/verification.md` when a field is disputed or an
arbiter error is ambiguous.

**Done when** the FEN prints `ARBITER: PASS`, or the position is explicitly
reported as printed-illegal together with the arbiter's errors.

## Step 6 — Report

Lead with the FEN in one fenced block, then the small provenance table:

| Field | Value | Source |
|---|---|---|
| Turn | `w` | default (caption not read) |
| Castling | `-` | not printed |
| En passant | `-` | not printed |
| Halfmove / fullmove | `0 1` | not printed |
| Orientation | White at bottom | printed rank-1 label / OCR+rules / default |

The board placement is the claim; the metadata is the assumption. If any square
remains uncertain, name it and give the alternative instead of hiding it behind
a confidence score. If the position is illegal, say so and quote the arbiter's
errors.

**Done when** the answer contains the FEN, the provenance table, and every
uncertain square with its alternative.

## When the board fights back

- **Board missing, multiple boards, orientation, skew**: the branch and its
  exact flags are in `references/ocr.md` §“If a board is still missed”. The
  short version: `stage` to see the detected box, then `--bbox`,
  `--board-index`, or `--orientation black|white`.
- **Model cannot run**: install the model, or fall back to the ledger workflow in
  `references/manual.md`. It is slower and more error-prone.
- **Cropped or illegal diagram**: do not invent the missing edge; ask for a
  complete board. If the printed position is genuinely illegal, report it as
  printed and quote the arbiter's errors.

## References

- `references/ocr.md` — model classes, the multi-pass merge, confidence flags,
  orientation order, thresholds, and board-search debugging.
- `references/manual.md` — the full read → second read → adjudicate → audit
  workflow when the model cannot run.
- `references/recognition.md` — piece silhouettes, lettered alphabets, printed
  artifacts, and ambiguity rules.
- `references/verification.md` — the six FEN fields, legality diagnosis, and
  what each arbiter failure usually means.
