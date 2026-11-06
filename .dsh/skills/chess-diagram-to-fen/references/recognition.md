# Recognition reference

The primary path is model-first: `solve` finds the board, reads all pieces with
2d-chess-ocr, and writes a 64-square audit. This file is for **auditing** those
labels and for the manual fallback when the model cannot run. Read it when the
diagram is not a standard Staunton figurine set, or when a square is small,
low-contrast, lettered, or covered by an annotation.

## Model-first reading

- The detector reads the **whole board**; the skill assigns each box centre to a
  square. Cropping one cell and running the detector on it does not work — the
  piece fills the frame and the model loses board context.
- The model runs at two context margins and, when needed, at both 180° orientations.
  Agreement between passes raises confidence; disagreement and low confidence are
  recorded as review flags.
- The model is strongest on modern figurine sets and clean screenshots. Small
  old woodcuts, unusual piece sets, and lettered diagrams need the audit more,
  not less: a high-confidence wrong label is possible.
- `review.png` shows the flagged cells with their alternatives. It is a triage
  aid, not a substitute for the full 64-square audit in `audit_q1..q4.png`.
- If the model cannot run, use the manual read → second read → adjudicate →
  audit sequence below and in `SKILL.md` “Manual fallback”.

## Decision order for one square

1. **Empty or occupied?** A piece has a body with a base; a shadow, arrowhead, or highlight does not.
2. **Letter or figurine?** Lettered diagrams put a character in the square; figurines are silhouettes.
3. **If lettered, which alphabet?** Identify the book's language before mapping letters (table below). `R` is a rook in English but a king in French, Spanish, and Italian; `B` is a bishop in English but a pawn in German.
4. **If a figurine, which silhouette?** Use the top profile and the negative space, not the overall size alone.
5. **Which colour?** Solid dark fill usually means Black; light fill with a dark contour usually means White. Confirm on several pieces before trusting it.
6. **Does context force a re-look?** More than one king, a pawn on rank 1/8, or a side with 17 pieces means a classification is wrong somewhere.
7. **Still torn?** Zoom the square with context and compare both reads. Record the cue you used.

## Orientation

The skill applies this order automatically; use it manually only when overriding.

1. **Printed coordinates are ground truth.** The detector recognizes the printed
   digit `1` (class 13) beside the rank labels. Bottom → White at bottom; top →
   Black at bottom. Do not assume the bottom-left is a1.
2. **No labels: chess rules + OCR evidence.** Both the upright and 180°-rotated
   board are read. The correct orientation yields ~30 well-recognized pieces and
   a legal position; the wrong one yields a handful of upside-down pieces and
   illegal pawn ranks/kings.
3. **Tie: White at bottom.** The book convention is an assumption, recorded as
   `default`; it is not evidence.
4. `--orientation white|black` or `--flip` overrides and is recorded as `user`.

- **Square colour cannot orient the board.** A 180° rotation maps every dark
  square to a dark square and every light square to a light square, so a
  standard-coloured board looks standard from either side. The a1-dark rule only
  confirms the colouring convention, not who is at the bottom.
- Captions like "White to move" do not state the viewpoint. "From Black's
  perspective", "Black at bottom", or a printed Black-to-move marker near the
  top does.
- Piece placement can corroborate but never overrule printed labels: kings on
  rank 1/8, queens on d1/d8, pawn masses on ranks 2/7. A position with both sides
  castled or advanced gives weak evidence.
- After `solve`, check `audit.png`’s corner labels and the report’s
  `orientation_source`. If the printed top-left was h1, the board needs a flip;
  `apply` cannot fix orientation — rerun with `--orientation black`.

## Figurine silhouettes

| Piece | Decisive cue | Often confused with |
|---|---|---|
| Pawn `P/p` | Smallest body; round ball head on a short neck; simple flared base; no crown, cross, or slit. | Bishop at small size (bishop has a pointed mitre and slit); a shadow or dot. |
| Rook `R/r` | Flat, crenellated top — the only castellated silhouette; straight tower body. | Queen only if the coronet is blurred into a block. |
| Knight `N/n` | Horse head and neck, ears, protruding muzzle; the only asymmetric glyph with a face. | Bishop at 20 px if the muzzle is lost. Look for the ear notch and the gap under the jaw. |
| Bishop `B/b` | Tall pointed mitre with a diagonal slit; small ball finial; symmetric body. | Pawn (round head, no slit); queen (queen has a multi-point coronet, not a single point). |
| Queen `Q/q` | Coronet with several points, balls, or fleur-de-lis; wide body; no cross. | King (king has a cross); rook (rook has a flat top). |
| King `K/k` | Cross on top of a crown; usually the tallest piece; broad base. | Queen when the cross is tiny; a queen's central coronet point can look like a cross at low resolution. |

Size order is only a tiebreaker: pawn < knight ≈ bishop < rook ≈ queen < king. Perspective, piece style, and the printer's font can invert it.

Useful negative spaces: the gap between a knight's muzzle and neck, the slit through a bishop's mitre, the balls on a queen's coronet, the cross arms on a king, the notches on a rook's top.

## Colour

- **Solid vs outline** is more reliable than hue. Black pieces are usually solid; White pieces are usually hollow or white-filled with a dark outline.
- A white piece on a light square is defined by its outline; a black piece on a dark square may have a thin white keyline. The keyline is not a white piece.
- Two-colour printing (black + red, or black + blue) may use the second ink for one side. If both sides look solid, check the letter case or a legend; do not assume the red pieces are White.
- Reversed/negative diagrams exist. If the side on ranks 1–2 is solid dark and the side on ranks 7–8 is outline, the colours are inverted relative to the usual convention; trust the letter case or caption, and record the anomaly.
- Hatching, stippling, or a grey screen can mark White pieces in monochrome printing. At low resolution it reads as a dirty fill; zoom before deciding.

## Lettered diagrams

| Language | King | Queen | Rook | Bishop | Knight | Pawn |
|---|---|---|---|---|---|---|
| English | `K` | `Q` | `R` | `B` | `N` (old `Kt`) | `P` |
| German | `K` | `D` | `T` | `L` | `S` | `B` |
| French | `R` | `D` | `T` | `F` | `C` | `P` |
| Spanish | `R` | `D` | `T` | `A` | `C` | `P` |
| Italian | `R` | `D` | `T` | `A` | `C` | `P` |
| Russian | `Кр` | `Ф` | `Л` | `С` | `К` | `П` |

- Case usually encodes colour: uppercase White, lowercase Black. Some books use uppercase for both and rely on colour; some reverse case. Check the legend or a known starting position.
- `B` is a landmine: English bishop, German pawn (Bauer). `R` is English rook but Romance-language king (roi/rey/re). `C` is a knight in French/Spanish/Italian, not a bishop. `D` is a queen in German/Romance languages (Dame/Dama/Donna).
- Russian letters are Cyrillic, not Latin lookalikes: `С` is bishop (слон), `К` is knight (конь), `Кр` is king.
- Strip colour prefixes/suffixes (`wK`, `Kb`, `K+`) before mapping; a trailing `+` is a check mark, not part of the piece.
- A lettered diagram may print a tiny coordinate inside the square; do not read it as the piece letter.

## Printed artifacts

- **Arrows**: long shaft plus arrowhead, often blue or red. They can cover a piece's body. Trace the outline on both sides of the shaft; the arrowhead is not a piece. A piece under an arrow still has its base and top.
- **Highlights**: a coloured square fill behind a piece (last move, check, key square). Ignore the fill; it can tint a white piece and lower contrast.
- **Check marks, circles, crosses, "x"**: annotations. A red `x` on a square is not a piece.
- **Last-move shading**: two adjacent squares tinted; the pieces on them are still the pieces.
- **Coordinates inside squares**: small a–h/1–8 characters in a corner, usually grey. Not pieces.
- **Board border and caption**: outside the playing grid; the 9 grid lines delimit the 64 squares.
- **3D/shadowed sets**: a cast shadow can look like a second pawn. The glyph body sits in the square centre; the shadow usually falls to one side.
- **Scan artifacts**: show-through from the reverse page, fold lines, speckles, JPEG halos. They create false edges but rarely a complete piece silhouette. The second read is the defence.
- **Hand corrections**: a printed piece crossed out with another drawn beside it. Treat the correction as the position but record it; if the intent is unclear, ask.

## Ambiguity rules

- **Two kings**: one of the cross-topped glyphs is a queen or a promoted piece, or a king was missed on another square. Find the other king before deciding.
- **Pawn on rank 1 or 8**: the glyph is not a pawn. Re-read it as bishop, queen, rook, or a letter; a pawn cannot stand there.
- **A piece crossing a grid line**: classify by the square containing its centre and base, not by the part that spills over.
- **A square that looks empty but has a sliver of a piece**: if the sliver connects to a piece centred in a neighbouring square, the square is empty. If the sliver is centred in this square, inspect it.
- **Bishop colour**: original bishops are bound to opposite colours. Three or more bishops on one side imply promotion; do not "fix" the count.
- **Promoted pieces**: extra queens/rooks/bishops/knights are legal if the side has ≤16 pieces and ≤8 pawns. Trust the image and flag the count, not the square.
- **A glyph under an arrow**: use the base and top profile; if the arrow hides the head, the base plus the square's context often decides. If not, inspect and note.
- **A letter that matches two languages**: resolve the alphabet from the book title, caption, or another unambiguous letter (e.g., a `D` on d1 with a `K` on e1 implies German/Romance queen, not English).

## Reading discipline

- In the normal path, the question for each square is **“does this tag match the
  printed piece?”**, not “what piece is this?”. Verification is easier and more
  reliable than a from-scratch read.
- Audit all four quadrant images (`audit_q1..q4.png`). The review sheet only
  covers flagged squares; a confident miss will not appear there.
- Use the printed coordinates to navigate, not memory of "the knight was around
  here".
- Before leaving a quadrant, check that every label sits on a piece of the same
  colour and type, and that every dot is really empty.
- A contextual impossibility is a reason to zoom, not a reason to change the
  square. The image is the source of truth; the rules only tell you where to look
  again.
- In the manual fallback, the quadrant images are the primary read and the
  half-board images are the independent second read. Do not use the same crop
  twice and call it independent. Read the square centre, write the symbol
  immediately, then move on. Before leaving a quadrant, check that every rank
  segment has exactly 4 symbols.
