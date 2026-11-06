"""FEN syntax, chess-rule validation, and square-level diagnosis.

python-chess is the primary arbiter.  A few rules it does not enforce (adjacent
kings, promotion material accounting) are checked here as well.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from .constants import (
    DEFAULT_CASTLING, DEFAULT_EP, DEFAULT_FULLMOVE, DEFAULT_HALFMOVE,
    DEFAULT_TURN, FEN_PIECES,
)
from .imaging import square_index, square_name

try:  # python-chess is a hard requirement for the full check, but degrade politely
    import chess  # type: ignore
except ImportError:  # pragma: no cover - depends on install
    chess = None


# --------------------------------------------------------------------- ledger/FEN
def parse_ledger(text: str) -> tuple[list[list[str]] | None, list[str]]:
    errors: list[str] = []
    rows: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(line)
    if len(rows) != 8:
        return None, [f"ledger needs exactly 8 non-comment lines, found {len(rows)}"]
    grid: list[list[str]] = []
    for i, row in enumerate(rows):
        if len(row) != 8:
            errors.append(f"rank line {i + 1} has {len(row)} characters, need 8: {row!r}")
            continue
        bad = sorted({ch for ch in row if ch not in FEN_PIECES and ch != "."})
        if bad:
            errors.append(f"rank line {i + 1} has invalid characters: {''.join(bad)!r}")
        grid.append(list(row))
    if len(grid) != 8:
        return None, errors
    return grid, errors


def ledger_to_fen(grid: Sequence[Sequence[str]]) -> str:
    parts = []
    for row in grid:
        out: list[str] = []
        empty = 0
        for ch in row:
            if ch == ".":
                empty += 1
            else:
                if empty:
                    out.append(str(empty))
                    empty = 0
                out.append(ch)
        if empty:
            out.append(str(empty))
        parts.append("".join(out))
    return "/".join(parts)


def fen_from_grid(grid: Sequence[Sequence[str]], turn: str = DEFAULT_TURN,
                  castling: str = DEFAULT_CASTLING, ep: str = DEFAULT_EP,
                  halfmove: int = DEFAULT_HALFMOVE,
                  fullmove: int = DEFAULT_FULLMOVE) -> str:
    return (f"{ledger_to_fen(grid)} {turn} {castling or '-'} {ep or '-'} "
            f"{halfmove} {fullmove}")


def parse_fen(fen: str) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    fields = fen.strip().split()
    if len(fields) != 6:
        return None, [f"FEN needs 6 space-separated fields, found {len(fields)}"]
    board_part, turn, castling, ep, half, full = fields
    if turn not in ("w", "b"):
        errors.append(f"active color must be w or b, found {turn!r}")
    rows = board_part.split("/")
    if len(rows) != 8:
        return None, [f"board field needs 8 ranks, found {len(rows)}"]
    grid: list[list[str]] = []
    for r, row in enumerate(rows):
        cells: list[str] = []
        prev_digit = False
        for ch in row:
            if ch.isdigit():
                if ch == "0":
                    errors.append(f"rank {8 - r}: digit 0 is not valid")
                    prev_digit = True
                    continue
                if prev_digit:
                    errors.append(
                        f"rank {8 - r}: adjacent digits {row!r} are not a valid empty run")
                cells.extend(["."] * int(ch))
                prev_digit = True
            elif ch in FEN_PIECES:
                cells.append(ch)
                prev_digit = False
            else:
                errors.append(f"rank {8 - r}: invalid character {ch!r}")
                prev_digit = False
        if len(cells) != 8:
            errors.append(f"rank {8 - r} expands to {len(cells)} squares, need 8")
            continue
        grid.append(cells)
    if len(grid) != 8:
        return None, errors
    if not re.fullmatch(r"\d+", half):
        errors.append(f"halfmove clock must be a non-negative integer, found {half!r}")
    if not re.fullmatch(r"\d+", full):
        errors.append(f"fullmove number must be a positive integer, found {full!r}")
    elif int(full) < 1:
        errors.append(f"fullmove number must be at least 1, found {full!r}")
    if castling != "-" and not re.fullmatch(r"[KQkq]+", castling):
        errors.append(f"castling field {castling!r} must be '-' or KQkq letters")
    if ep != "-" and not re.fullmatch(r"[a-h][36]", ep):
        errors.append(f"en passant target {ep!r} is not a valid square")
    meta = {"turn": turn, "castling": castling, "ep": ep,
            "halfmove": half, "fullmove": full}
    return {"grid": grid, "meta": meta, "fen": " ".join(fields)}, errors


def grid_counts(grid: Sequence[Sequence[str]]) -> dict:
    counts = {side: {k: 0 for k in "kqrbnp"} for side in ("white", "black")}
    for row in grid:
        for ch in row:
            if ch == ".":
                continue
            side = "white" if ch.isupper() else "black"
            counts[side][ch.lower()] += 1
    for side in counts:
        counts[side]["total"] = sum(counts[side].values())
    return counts


def counts_line(counts: dict) -> str:
    parts = []
    for side in ("white", "black"):
        c = counts[side]
        detail = " ".join(
            f"{k.upper() if side == 'white' else k}{c[k]}" for k in "kqrbnp")
        parts.append(f"{side.capitalize()}: {detail} = {c['total']}")
    return " | ".join(parts)


def ascii_board(grid: Sequence[Sequence[str]]) -> str:
    lines = ["    a b c d e f g h"]
    for r in range(8):
        cells = " ".join(ch if ch in FEN_PIECES else "." for ch in grid[r])
        lines.append(f"  {8 - r} {cells}  {8 - r}")
    lines.append("    a b c d e f g h")
    return "\n".join(lines)


def find_squares(grid: Sequence[Sequence[str]], wanted: str) -> list[str]:
    return [square_name(r, c) for r in range(8) for c in range(8) if grid[r][c] == wanted]


def attacked(grid: Sequence[Sequence[str]], rank_i: int, file_i: int,
             by_white: bool) -> bool:
    """Is the square attacked by the given side? (No python-chess needed.)"""
    if by_white:
        for df in (-1, 1):
            r, c = rank_i + 1, file_i + df
            if 0 <= r < 8 and 0 <= c < 8 and grid[r][c] == "P":
                return True
    else:
        for df in (-1, 1):
            r, c = rank_i - 1, file_i + df
            if 0 <= r < 8 and 0 <= c < 8 and grid[r][c] == "p":
                return True
    for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                   (1, -2), (1, 2), (2, -1), (2, 1)):
        r, c = rank_i + dr, file_i + dc
        if 0 <= r < 8 and 0 <= c < 8:
            piece = grid[r][c]
            if (by_white and piece == "N") or (not by_white and piece == "n"):
                return True
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = rank_i + dr, file_i + dc
            if 0 <= r < 8 and 0 <= c < 8:
                piece = grid[r][c]
                if (by_white and piece == "K") or (not by_white and piece == "k"):
                    return True
    for dr, dc, kinds in ((-1, 0, "RQ"), (1, 0, "RQ"), (0, -1, "RQ"),
                          (0, 1, "RQ"), (-1, -1, "BQ"), (-1, 1, "BQ"),
                          (1, -1, "BQ"), (1, 1, "BQ")):
        r, c = rank_i + dr, file_i + dc
        while 0 <= r < 8 and 0 <= c < 8:
            piece = grid[r][c]
            if piece != ".":
                if piece.isupper() == by_white and piece.upper() in kinds:
                    return True
                break
            r += dr
            c += dc
    return False


# --------------------------------------------------------------------- validation
@dataclass
class Issue:
    code: str
    message: str
    squares: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "squares": list(self.squares)}


@dataclass
class Validation:
    legal: bool
    errors: list[Issue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    python_chess: str = "not installed"
    counts: dict = field(default_factory=dict)
    suspect_squares: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "legal": self.legal,
            "python_chess": self.python_chess,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": list(self.warnings),
            "counts": self.counts,
            "suspect_squares": list(self.suspect_squares),
        }


def _square_name(chess_square) -> str:
    if chess is not None and isinstance(chess_square, int):
        return chess.square_name(chess_square)
    return chess_square.name if hasattr(chess_square, "name") else str(chess_square)


def _attackers_to(board, colour, square) -> list[str]:
    try:
        return sorted(_square_name(sq) for sq in board.attackers(colour, square))
    except Exception:
        return []


def validate_grid(grid: Sequence[Sequence[str]], turn: str = DEFAULT_TURN,
                  castling: str = DEFAULT_CASTLING, ep: str = DEFAULT_EP) -> Validation:
    """Validate an 8x8 placement plus the metadata that matters for legality."""
    counts = grid_counts(grid)
    errors: list[Issue] = []
    warnings: list[str] = []

    for side in ("white", "black"):
        if counts[side]["k"] != 1:
            king_squares = find_squares(grid, "K" if side == "white" else "k")
            errors.append(Issue(
                "king-count",
                f"{side}: {counts[side]['k']} kings (need exactly 1)",
                king_squares))
        if counts[side]["total"] > 16:
            errors.append(Issue(
                "piece-count", f"{side}: {counts[side]['total']} pieces (max 16)",
                [square_name(r, c) for r in range(8) for c in range(8)
                 if grid[r][c] != "." and grid[r][c].isupper() == (side == "white")]))
        if counts[side]["p"] > 8:
            errors.append(Issue(
                "pawn-count", f"{side}: {counts[side]['p']} pawns (max 8)",
                find_squares(grid, "P" if side == "white" else "p")))

    for r in range(8):
        for c in range(8):
            if grid[r][c] in "Pp" and r in (0, 7):
                errors.append(Issue(
                    "pawn-backrank",
                    f"pawn on {square_name(r, c)} (rank {8 - r}) cannot be a pawn",
                    [square_name(r, c)]))

    wk_sq, bk_sq = find_squares(grid, "K"), find_squares(grid, "k")
    adjacent_kings = False
    if len(wk_sq) == 1 and len(bk_sq) == 1:
        wr, wc = square_index(wk_sq[0])
        br, bc = square_index(bk_sq[0])
        if abs(wr - br) <= 1 and abs(wc - bc) <= 1:
            adjacent_kings = True
            errors.append(Issue(
                "adjacent-kings", "kings are adjacent", [wk_sq[0], bk_sq[0]]))

    # Promotion accounting: a side cannot have more non-pawns than its original
    # seven plus one per missing pawn.
    for side in ("white", "black"):
        pawns = counts[side]["p"]
        nonpawns = sum(counts[side][p] for p in "qrbn")
        if nonpawns > 7 + (8 - pawns):
            squares = [square_name(r, c) for r in range(8) for c in range(8)
                       if grid[r][c] != "." and grid[r][c].isupper() == (side == "white")
                       and grid[r][c].lower() != "p"]
            errors.append(Issue(
                "promotion-material",
                f"{side}: {nonpawns} non-pawn pieces with {pawns} pawns "
                f"(impossible without enough promotion)",
                squares))

    if turn not in ("w", "b"):
        errors.append(Issue("turn", f"active color {turn!r} is not w/b", []))
    if castling != "-":
        if not re.fullmatch(r"[KQkq]+", castling) or len(set(castling)) != len(castling):
            errors.append(Issue(
                "castling-field",
                f"castling field {castling!r} must be '-' or unique letters KQkq", []))
        else:
            need = {
                "K": ("e1", "h1", "K", "R"),
                "Q": ("e1", "a1", "K", "R"),
                "k": ("e8", "h8", "k", "r"),
                "q": ("e8", "a8", "k", "r"),
            }
            for ch in castling:
                ksq, rsq, kp, rp = need[ch]
                if grid[square_index(ksq)[0]][square_index(ksq)[1]] != kp or \
                   grid[square_index(rsq)[0]][square_index(rsq)[1]] != rp:
                    errors.append(Issue(
                        "castling-material",
                        f"castling right {ch!r} requires {kp} on {ksq} "
                        f"and {rp} on {rsq}", [ksq, rsq]))
    if ep != "-":
        if not re.fullmatch(r"[a-h][36]", ep):
            errors.append(Issue("ep-field", f"en passant target {ep!r} is not a square", []))
        else:
            er, ec = square_index(ep)
            if turn == "w":
                if er != 2:
                    errors.append(Issue(
                        "ep-rank", f"en passant target {ep} must be on rank 6 "
                        "when White moves", [ep]))
                pawn_r, pawn = er + 1, "p"
            else:
                if er != 5:
                    errors.append(Issue(
                        "ep-rank", f"en passant target {ep} must be on rank 3 "
                        "when Black moves", [ep]))
                pawn_r, pawn = er - 1, "P"
            if not (0 <= pawn_r < 8) or grid[pawn_r][ec] != pawn:
                errors.append(Issue(
                    "ep-pawn", f"en passant {ep}: no {pawn!r} on "
                    f"{square_name(pawn_r, ec)}", [ep, square_name(pawn_r, ec)]))
            if grid[er][ec] != ".":
                errors.append(Issue(
                    "ep-occupied", f"en passant target square {ep} is occupied", [ep]))

    # python-chess: syntax + most legality rules, plus check/attack analysis.
    status_text = "not installed"
    if chess is not None:
        try:
            board = chess.Board(fen_from_grid(grid, turn, castling, ep))
        except ValueError as exc:
            errors.append(Issue("fen-rejected", f"python-chess rejected the FEN: {exc}", []))
            status_text = "rejected"
            board = None
        if board is not None:
            if board.is_valid():
                status_text = "valid"
            else:
                flags = [flag.name for flag in chess.Status
                         if flag != chess.Status.VALID and (board.status() & flag)]
                status_text = "invalid (" + ", ".join(flags) + ")" if flags \
                    else "invalid"
            if not board.is_valid():
                _add_status_issues(board.status(), errors)
            wk = board.king(chess.WHITE)
            bk = board.king(chess.BLACK)
            if wk is not None and bk is not None:
                white_check = board.is_attacked_by(chess.BLACK, wk)
                black_check = board.is_attacked_by(chess.WHITE, bk)
                if adjacent_kings:
                    pass
                elif white_check and black_check:
                    errors.append(Issue(
                        "both-in-check", "both kings are in check",
                        [_square_name(wk), _square_name(bk)]))
                elif turn == "w" and black_check:
                    errors.append(Issue(
                        "opposite-check",
                        "Black is in check but it is White's turn (illegal)",
                        [_square_name(bk)] + _attackers_to(board, chess.WHITE, bk)))
                elif turn == "b" and white_check:
                    errors.append(Issue(
                        "opposite-check",
                        "White is in check but it is Black's turn (illegal)",
                        [_square_name(wk)] + _attackers_to(board, chess.BLACK, wk)))
    else:
        warnings.append("python-chess is not installed; using the built-in checks only")
        if len(wk_sq) == 1 and len(bk_sq) == 1 and not adjacent_kings:
            wr, wc = square_index(wk_sq[0])
            br, bc = square_index(bk_sq[0])
            white_check = attacked(grid, wr, wc, False)
            black_check = attacked(grid, br, bc, True)
            if white_check and black_check:
                errors.append(Issue(
                    "both-in-check", "both kings are in check", [wk_sq[0], bk_sq[0]]))
            elif turn == "w" and black_check:
                errors.append(Issue(
                    "opposite-check",
                    "Black is in check but it is White's turn (illegal)",
                    [bk_sq[0]]))
            elif turn == "b" and white_check:
                errors.append(Issue(
                    "opposite-check",
                    "White is in check but it is Black's turn (illegal)",
                    [wk_sq[0]]))

    # Deduplicate by message, keeping the union of implicated squares.
    merged: dict[str, Issue] = {}
    for issue in errors:
        if issue.message in merged:
            merged[issue.message].squares = sorted(
                set(merged[issue.message].squares) | set(issue.squares))
        else:
            merged[issue.message] = issue
    errors = list(merged.values())

    suspect = sorted({sq for issue in errors for sq in issue.squares if sq})
    return Validation(not errors, errors, warnings, status_text, counts, suspect)


def _add_status_issues(status, errors: list[Issue]) -> None:
    if chess is None:
        return
    # Most statuses duplicate the explicit checks above; only add the ones that
    # need python-chess's attack analysis.
    mapping = {
        chess.Status.IMPOSSIBLE_CHECK: (
            "impossible-check", "impossible check", []),
        chess.Status.TOO_MANY_CHECKERS: (
            "too-many-checkers", "too many checkers", []),
    }
    for flag, (code, message, squares) in mapping.items():
        if flag == chess.Status.VALID:
            continue
        if status & flag:
            errors.append(Issue(code, message, list(squares)))


def validate_fen(fen: str) -> Validation:
    parsed, syntax = parse_fen(fen)
    if parsed is None:
        errors = [Issue("fen-syntax", msg, []) for msg in syntax]
        return Validation(False, errors, [], "rejected", {}, [])
    v = validate_grid(parsed["grid"], parsed["meta"]["turn"],
                      parsed["meta"]["castling"], parsed["meta"]["ep"])
    if syntax:
        v.errors.extend(Issue("fen-syntax", msg, []) for msg in syntax)
        v.legal = False
        v.suspect_squares = sorted({sq for e in v.errors for sq in e.squares})
    return v


def orientation_penalty(grid: Sequence[Sequence[str]]) -> dict:
    """Score one orientation by the best legal reading under either turn.

    Using both turns keeps a Black-to-move diagram from being flipped just
    because its king happens to be in check.
    """
    options = []
    for turn in ("w", "b"):
        v = validate_grid(grid, turn)
        options.append({"turn": turn, "penalty": len(v.errors),
                        "errors": [e.message for e in v.errors],
                        "suspects": v.suspect_squares})
    best = min(options, key=lambda o: o["penalty"])
    return best


def flipped_grid(grid: Sequence[Sequence[str]]) -> list[list[str]]:
    return [[grid[7 - r][7 - c] for c in range(8)] for r in range(8)]
