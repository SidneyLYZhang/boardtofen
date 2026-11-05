---
name: chess-diagram-to-fen
description: Read a printed or on-screen 2D chess diagram and return a verified FEN. Use when converting a board image to FEN, or checking an existing FEN against a diagram.
compatibility: "Python 3.10+ with Pillow and NumPy; python-chess optional."
license: "MIT (software) / CC0-1.0 (documentation)"
---

# Chess diagram → FEN

A diagram gives 64 facts and no history. One careful look is not enough: **two independent reads** must agree on every square, and an **audit image** must show every FEN label sitting on the piece it claims. The helper script stages labeled views, diffs the reads, assembles the FEN, and checks legality; you do the recognition.

Run commands from this skill's directory, or prefix `scripts/boardtool.py` with its absolute path. Python 3.10+ with Pillow and NumPy (`python -m pip install -r requirements.txt`); `check` also uses python-chess when installed. After installing, run `python scripts/selftest.py` to verify the toolchain end to end. If the helper cannot run, follow the same read → second read → adjudicate → audit sequence by hand; the sequence is the skill.

## Step 1 — Read the page, then stage the board

Open the original image once and look at the margins, not the squares:

- printed file/rank labels, and which corner is a8;
- caption: side to move, castling or en-passant notes, "from Black's perspective";
- arrows, highlights, last-move marks, diagram number.

Orientation is the one fact a position cannot supply: a 180° rotation preserves square colours and can turn one legal-looking position into another. Printed coordinates are ground truth. Without them, the book convention is White at bottom; record that as an assumption. A diagram printed from Black's side is upside down for FEN — stage it with `--flip`.

```bash
python scripts/boardtool.py prepare board.png --out work
```

This writes `work/board.json`, `overlay.png`, `contact.png`, four 4×4 quadrants `q1`–`q4`, and two 8×4 halves. Open `overlay.png`: every red line must sit on a printed grid line, including the four edges. If the grid drifts or the box is wrong, run `grid`, read the pixel coordinates of the board's outer grid lines, and rerun `prepare --bbox x0,y0,x1,y1` (a manual bbox skips deskew).

Write `work/notes.md` before reading squares: orientation evidence, turn evidence (quote the caption or write `assumed`), and any annotation to ignore.

**Done when** `overlay.png` passes and the notes name the orientation and turn evidence.

## Step 2 — First read: quadrant sweep

Read `q1` → `q4` in order, one image at a time. For every square write one character:

| White | Black | Empty |
|---|---|---|
| `K Q R B N P` | `k q r b n p` | `.` |

Use the FEN letters now, not names. Read from the square's centre, and write the row before moving on. A tall piece may cross the printed grid line; the square's centre decides. If a glyph is not nameable in two seconds, open `references/recognition.md` before guessing — it carries the silhouette cues, letter alphabets, and printed-artifact traps.

Build `work/read1.txt`: exactly 8 rows, rank 8 first, 8 characters per row. If your file-write tool is unavailable, `write-ledger` creates and validates the format:

```bash
python scripts/boardtool.py write-ledger --out work/read1.txt \
  --rows "rnbqkbnr,pppppppp,........,........,........,........,PPPPPPPP,RNBQKBNR"
```

The example is the starting position; replace the rows with the diagram's. `write-ledger` checks only the 8×8 format — `counts` still gates the position.

```bash
python scripts/boardtool.py counts work/read1.txt
```

`counts` is the structural gate: one king per side, no pawn on rank 1/8, piece and pawn totals sane. If it fails, fix the named squares before going on.

**Done when** `read1.txt` has 8×8 symbols and `counts` prints `LEDGER: structurally OK`.

## Step 3 — Blind second read: half-board sweep

Write `work/read2.txt` from the image alone; do not open `read1.txt` first. Read `half_bottom.png` before `half_top.png`, so the traversal differs from the quadrant sweep: a different cut, a different order, the same 64 answers.

```bash
python scripts/boardtool.py compare work/read1.txt work/read2.txt
```

`compare` names every differing square with both symbols. Differences are the useful output, not a failure.

**Done when** both reads exist and `compare` has run.

## Step 4 — Adjudicate every difference

```bash
python scripts/boardtool.py inspect --board work/board.json \
  --squares e4,e5,f6 --out work/disputes.png
```

Replace the example squares with the ones `compare` named. Each tile is upscaled, outlined in red, and includes neighbouring squares for context. Decide by silhouette first, context second. Record in `notes.md`: square, first read, second read, decision, cue. If a difference survives inspection, get a fresh read — a subagent given only the image and this protocol — or ask the user; do not pick the more plausible piece.

Write the resolved board to `work/final.txt`. Both comparisons should now show only adjudicated squares:

```bash
python scripts/boardtool.py compare work/read1.txt work/final.txt
python scripts/boardtool.py compare work/read2.txt work/final.txt
```

**Done when** `final.txt` is 8×8, every original difference is in the notes, and both comparisons are explained.

## Step 5 — Encode and arbitrate

```bash
python scripts/boardtool.py fen --ledger work/final.txt \
  --turn w --castling - --ep - --halfmove 0 --fullmove 1
```

Default `w - - 0 1`; change a field only when the page states it. Castling rights cannot be seen in a diagram — `-` unless the caption explicitly gives them. En passant is `-` unless a last-move caption marks a two-square pawn push. A diagram encodes placement, not history; invented metadata is less accurate than `-`. Read `references/verification.md` when a field is stated, disputed, or the arbiter objects.

```bash
python scripts/boardtool.py check "<FEN>"
```

`check` prints the ASCII board, counts, metadata, and python-chess's verdict. A legal position can still be wrong: legality is not truth. The arbiter catches impossible counts and checks, not a misread that happens to be legal.

**Done when** `ARBITER: PASS`. If it fails, treat each error as a pointer to squares to re-read, never as permission to move a piece to make the position legal.

## Step 6 — Audit the FEN against the image

This is the step that catches a legal-but-wrong FEN.

```bash
python scripts/boardtool.py annotate --board work/board.json \
  --fen "<FEN>" --out work/audit.png
```

Open `audit.png` and scan all 64 squares: every red uppercase letter must sit on a White piece of that type, every blue lowercase letter on a Black piece, every dot on an empty square. A label on the wrong square or on emptiness is a mismatch; fix `final.txt`, re-encode, and audit again. For dense or disputed boards, also render the FEN and compare the two boards:

```bash
python scripts/boardtool.py render "<FEN>" --out work/reconstruction.png
```

**Done when** all 64 labels match the printed pieces and the FEN has not changed since the audit image was generated.

## Step 7 — Report

Lead with the FEN in one fenced block. Then the small provenance table:

| Field | Value | Source |
|---|---|---|
| Turn | `w` | caption "White to move" / assumed |
| Castling | `-` | not printed |
| En passant | `-` | not printed |
| Halfmove / fullmove | `0 1` | not printed |
| Orientation | White at bottom | printed coordinates |

The board placement is the claim; the metadata is the assumption. If any square remains uncertain, name it and give the alternative instead of hiding it behind a confidence score.

## When the board fights back

- **No detection**: `grid` → manual `--bbox`. Box the board's *outer grid lines*, not the paper edge.
- **Several diagrams on one page**: crop the target board first; each board is a separate transcription.
- **A crop that cuts off a rank, file, or piece**: the missing information is not recoverable. Ask for a complete board rather than inventing the edge.
- **Skew or perspective**: the detector handles small rotation; for a photographed page, crop and rectify first, then `prepare`.
- **Black's perspective**: `--flip`; the printed labels move with the pieces, so the contact image is normalized.
- **Illegal printed position**: report it as printed. A FEN can faithfully record an illegal diagram; the arbiter's errors explain why it is illegal.
- **Contested square after zoom**: fresh subagent read or user question. A coin flip is not a reading.

## References

- `references/recognition.md` — open when the piece set is not standard Staunton, uses letters or another language, is small or low-contrast, or a square is covered by an arrow or highlight.
- `references/verification.md` — open when setting the six FEN fields, interpreting an arbiter failure, or deciding whether an illegal-looking diagram is a misread.
