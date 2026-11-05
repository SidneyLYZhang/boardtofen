# Verification reference

Read this when setting the six FEN fields, when the arbiter objects, or when deciding whether an illegal-looking diagram is a misread or a genuinely illegal position.

## The six fields

A FEN has six space-separated fields: placement, active colour, castling, en passant, halfmove clock, fullmove number. Only the first is fully visible in a diagram.

### Placement

Eight ranks separated by `/`, rank 8 first. Files run a→h left to right. Uppercase is White, lowercase is Black. A digit compresses that many empty squares. Each rank must expand to exactly 8.

### Active colour

Set from the caption: "White to move", "Black to play", a small `W`/`B` marker, or the diagram's own note. If the page is silent, use `w` and record it as **assumed**. Do not infer the turn from the last-move arrow, the score, or which side "looks" better; only the caption or a marker states it.

### Castling

The field records rights, not possibilities. A diagram shows where the king and rooks stand, never whether they have moved. Use `-` unless the caption, PGN excerpt, or diagram legend explicitly gives rights. Do **not** add `KQkq` because the king and rooks happen to be on their home squares; that is the most common way a diagram-to-FEN answer becomes wrong.

`check` verifies that each claimed right has the king and rook on their home squares. Legal rights may still exist with pieces between them; that is not an error.

### En passant

Use `-` by default. Set a target square only when the page explicitly marks a two-square pawn advance as the last move:

- White to move: target is on rank 6; a Black pawn is on rank 5 on the same file; the target square is empty.
- Black to move: target is on rank 3; a White pawn is on rank 4; the target square is empty.

Mark an en-passant target as inferred. If the caption does not show the last move, `-` is the accurate answer even if an en passant capture might have been available in the original game.

### Halfmove and fullmove

The halfmove clock is the number of plies since the last capture or pawn move. The fullmove number starts at 1 and increments after Black's move. A diagram usually states neither; use `0 1` and record both as assumed. Only a caption, score sheet, or PGN excerpt can supply them.

## FEN syntax traps

- Ranks are written **top to bottom**: rank 8 first, rank 1 last. Writing the board bottom-up mirrors every piece.
- Each rank is compressed independently. An empty rank is `8`; a rank with one White queen on d1 is `3Q4`; the starting back rank is `RNBQKBNR`.
- Digits are 1–8. `0` and `9` are invalid. Two adjacent digits are not a valid run; merge them.
- `b` is a Black bishop; `B` is a White bishop. Case is colour, not piece type.
- A FEN with a missing or extra field is malformed even if the board looks right.
- Quote the FEN in a shell: `"rnbq... w - - 0 1"`. The spaces are field separators.

## Arbiter failures: what they usually mean

| Arbiter message | Likely cause | First action |
|---|---|---|
| `rank N expands to ...` | Wrong row length, misplaced digit, or a ledger line copied short. | Re-read that rank, then the row before it. |
| `N kings` | A king was missed, two king-like glyphs were read as kings, or colours are inverted. | Find both kings; zoom the cross-topped glyphs. |
| `pawn on ... rank 1/8` | A bishop/queen was read as a pawn, or the board is rank-reversed. | Zoom the square; check the neighbouring back rank. |
| `>16 pieces` or `>8 pawns` | A square was duplicated, colours are inverted, or both reads copied the same skip. | Compare the two ledgers; count pieces per side. |
| `Black is in check but it is White's turn` | The turn caption was misread, or a king/checking piece is misplaced. | Re-read the caption before moving any piece. |
| `both kings are in check` | At least one king is misread or two pieces are swapped. | Find both kings and their attackers. |
| `kings are adjacent` | A king is misread, or two squares are swapped. | Zoom both kings; re-check the back ranks. |
| `castling right ... requires ...` | Castling rights were invented, or the king/rook is misread. | Remove the right unless the page gives it; check e1/e8/h1/h8/a1/a8. |
| `en passant ... no pawn` | The en-passant target was invented, or a pawn rank is wrong. | Re-read the last-move caption and the pawn's rank. |
| `python-chess invalid` but no own error | A subtle legality issue (side not to move in check, impossible check count). | Inspect the status; still treat the image as source of truth. |
| `LEDGER: structurally OK` but the FEN is wrong | A legal misread. | Run the audit image; legality cannot catch it. |

## The audit is the truth check

`check` proves the FEN is well formed and legal. It does not prove the FEN matches the picture. A queen on e3 instead of f3 can be perfectly legal.

The final audit uses `annotate`: the FEN symbol is stamped into every source square, so the question becomes perceptual, not legal — does this label sit on the piece it names? On a lettered diagram the audit label is FEN's English letter, not the book's: translate first (`D`→`Q`, `T`→`R`, `L`→`B`, `S`→`N`). A printed `D` under a red `Q` is a match, not a mismatch.

Check all four quadrants, including empty squares. Pay special attention to:

- **Rank order**: the top row of the image is rank 8. If the bottom row is labelled 8, the board is upside down.
- **Colour**: in a starting-like position, White occupies ranks 1–2. Lowercase there means the colours are inverted.
- **The last row you read**: fatigue errors cluster at the end of a sweep. Re-read rank 1 and rank 8 deliberately.
- **Pieces under arrows or highlights**: the annotation label can confirm the identity you inferred.
- **Squares you "remember" as empty**: dots are data. Check them.

If the audit finds a mismatch, fix `final.txt`, rebuild the FEN, re-run `check`, and regenerate the audit image. Do not patch the FEN string directly; the ledger is the single source of truth.

## Reporting uncertainty

Use a provenance table rather than a confidence percentage:

| Field | Value | Source |
|---|---|---|
| Turn | `b` | caption "Black to play" |
| Castling | `-` | not printed |
| En passant | `-` | no last move shown |
| Halfmove / fullmove | `0 1` | not printed |
| Orientation | White at bottom | printed coordinates a–h / 1–8 |

If a square remains uncertain, name it and give the alternative (`e5: Black pawn or empty; the arrow obscures the head`). If the diagram is illegal, say so and show the arbiter's errors; the FEN can still be a faithful record of the printed position. Accuracy includes saying what the diagram does not tell you.
