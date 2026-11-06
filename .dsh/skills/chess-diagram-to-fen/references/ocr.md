# OCR model reference

Read this when the model misses a board or a piece, when confidence looks wrong,
or when changing thresholds.

## Model

The recognizer is the ONNX export of [2d-chess-ocr](https://github.com/AndrewSpano/2d-chess-ocr)
by Andreas Spanopoulos. The project is MIT; the ONNX file itself embeds an
AGPL-3.0 / Ultralytics license notice, so read `THIRD_PARTY_NOTICES.md` before
redistributing it. `scripts/download_model.py` places it in:

```text
scripts/models/2d-chess-ocr/yolo26m-finetuned.onnx   # default, 81.8 MB
scripts/models/2d-chess-ocr/yolo26n-finetuned.onnx   # optional, 9.8 MB
```

`m` is the accurate default; `n` is a fast fallback. Run
`download_model.py` once, or add `--download` to a `solve`/`stage`/`read`
command to fetch a missing model for that run. There is no implicit network
request. The model stays inside the skill directory; inference is local. See
`THIRD_PARTY_NOTICES.md` for the attribution and licensing note.

The export has one input, `images: [1, 3, 640, 640]`, and one output,
`output0: [1, 300, 6]` with rows `x1, y1, x2, y2, confidence, class_id`.
Coordinates are in the 640-pixel letterboxed frame. The detector wrapper also
decodes a standard Ultralytics `[1, 4 + nc, N]` export, so a re-export still
works.

## Classes

| id | class | FEN | id | class | FEN |
|---:|---|---|---:|---|---|
| 0 | chessboard | — | 8 | white_rook | `R` |
| 1 | black_pawn | `p` | 9 | white_bishop | `B` |
| 2 | black_rook | `r` | 10 | white_knight | `N` |
| 3 | black_bishop | `b` | 11 | white_king | `K` |
| 4 | black_knight | `n` | 12 | white_queen | `Q` |
| 5 | black_king | `k` | 13 | rank_one_id | orientation |
| 6 | black_queen | `q` | 14 | last_move_start_tile | turn hint |
| 7 | white_pawn | `P` | 15 | last_move_end_tile | turn hint |

Class 13 is the printed digit `1` beside a rank label. Its position (top or
bottom of the board) is the strongest orientation evidence a diagram can give.

## One solve, several views

`solve` runs the detector on more than one crop because a single view has blind
spots:

1. **Board search** on the full page at 640. If no board is found, overlapping
   tiles are tried, then the classical projection detector.
2. **Orientation passes** only when there are no printed rank-1 labels: the
   board crop is run upright and rotated 180°, then scored by piece evidence and
   chess legality.
3. **Two recognition passes** at 15% and 35% context margin around the board,
   plus the 25% orientation pass when it exists. The model sees the whole board
   each time; the views differ in scale and surrounding page.

Each pass assigns a detection to a square by the **centre** of its box. The
passes are reconciled per square:

- same symbol in both passes → confidence kept, support increases;
- different symbols → higher confidence wins, `pass-disagreement` is recorded,
  and both symbols appear in `review.png`;
- a symbol seen by only one pass → confidence is reduced and `single-pass` is
  recorded;
- no piece in any pass → empty square.

The model is a detector, not a per-tile classifier. Cropping a single 1/8 cell
and running the model on it does **not** work: pieces fill the frame and the
model loses the board context. The correct "per-square recognition" is
whole-board detection followed by the centre-to-square assignment above.

## Confidence and review flags

| flag | meaning | action |
|---|---|---|
| `low-confidence` | final confidence below `--review-conf` (default 0.75) | inspect the cell |
| `pass-disagreement` | the two views chose different symbols | inspect; the review sheet shows both |
| `single-pass` | only one view saw a piece | inspect; could be a miss in the other view |
| `close-alternative` | a second class is within 0.12 confidence | inspect; the silhouette decides |
| `low-confidence` + validator suspect | the position is also illegal at that square | fix the square, then recheck |

The detector is strong on modern figurine sets and screen diagrams. It is
weaker on small, old woodcut diagrams and on unusual lettered sets. Low
confidence and pass disagreement are the useful signals; a high-confidence
wrong piece is still possible, which is why the audit image covers all 64
squares.

## Orientation order

1. Printed rank-1 label (`rank_one_id`) near the bottom → White at bottom;
   near the top → Black at bottom. Two labels on both sides are summed by
   confidence. Printed coordinates normally win.
   Labels stay authoritative: both orientations are still read, and if the
   printed label's side has less than a third of the OCR evidence of the other
   (the other has ≥12 pieces and a more legal position), the report records a
   warning. It does **not** flip the board; an isolated `1.` that was mistaken
   for a rank label is resolved by inspecting the warning and passing
   `--orientation` explicitly.
2. Without labels, both board orientations are run. The orientation whose
   pieces are recognized (more high-confidence pieces) and whose FEN is legal
   under at least one side to move wins.
3. If both read equally well and both are legal, **White at bottom** is the
   default, as in the book convention.
4. `--orientation white|black` or `--flip` overrides all of the above and is
   recorded as `user`.

The wrong orientation is obvious to the model: the pieces are upside down, so
it usually finds only 5–15 pieces instead of ~32, and they have lower
confidence. A Black-at-bottom diagram is therefore normalized by rotating the
board crop 180° *before* splitting cells and running the final passes.

## Thresholds and when to change them

- `--conf 0.25` is the detector floor. Lower it only for very small pieces;
  it adds false positives. Raise it to 0.35–0.4 for noisy scans, then expect
  more `single-pass` flags.
- `--review-conf 0.75` controls which cells are called out. Raise it for a
  conservative audit; lower it to reduce the review sheet on clean screenshots.
- `--board-index N` selects a board on a multi-board page (0-based, reading
  order). Without it the largest board is used.
- `--bbox x0,y0,x1,y1` bypasses board detection entirely. Use it when the page
  contains a board the model refuses to see, or when the page has several
  boards and you want an exact crop. The box is the board's **outer grid
  lines**, not the paper edge.
- `--variant n` uses the small model. It is faster and smaller but noticeably
  weaker on book scans; prefer `m` unless download size or CPU is critical.

## If a board is still missed

1. Run `stage` to see the detected boxes and `overlay.png`.
2. Read the board's outer grid-line coordinates from `grid` (pixel labels) or an
   image editor.
3. Rerun with `--bbox`; then `read` to reuse the staged crop.
4. If the board is skewed or a phone photo, the built-in deskew handles a few
   degrees. Strong perspective needs a rectified crop first; the model assumes
   an axis-aligned 2D board.
