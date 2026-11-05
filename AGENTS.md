# Agent notes

This repository packages one Agent Skill: `chess-diagram-to-fen`.

- Canonical source: `.dsh/skills/chess-diagram-to-fen/`. Edit this copy, not an installed copy.
- To install it for a user or another agent, follow [`INSTALL.md`](INSTALL.md) §5 "给 agent 的安装协议". Copy the whole skill directory; do not flatten it or copy only `SKILL.md`.
- After changing the skill or its scripts, run `python .dsh/skills/chess-diagram-to-fen/scripts/selftest.py` and require `PASS`.
- `README.md` explains FEN and the FEN/PGN distinction; keep those sections accurate when editing.
- Licensing: software and scripts are MIT (`LICENSE-MIT`); documentation and skill text are CC0-1.0 (`LICENSE-CC0`). Keep the README license section consistent when editing.
