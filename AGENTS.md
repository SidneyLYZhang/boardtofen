# Agent notes

This repository packages one Agent Skill: `chess-diagram-to-fen`.

- Canonical source: `.dsh/skills/chess-diagram-to-fen/`. Edit this copy, not an installed copy.
- To install it for a user or another agent, follow [`INSTALL.md`](INSTALL.md) §5 "给 agent 的安装协议". Copy the whole skill directory; do not flatten it or copy only `SKILL.md`.
- The recognition model is not bundled. After installing, run `python .dsh/skills/chess-diagram-to-fen/scripts/download_model.py` (about 82 MB), then `python .dsh/skills/chess-diagram-to-fen/scripts/selftest.py`; require `PASS`.
- The model lives in `.dsh/skills/chess-diagram-to-fen/scripts/models/2d-chess-ocr/` and is gitignored. Selftest fails with a clear message when it is absent; `--download-model` may be used to fetch it.
- Repository tests live in `test/`; run `python test/run_tests.py`. Integration tests skip cleanly without ONNX Runtime or the model. Run both the tests and selftest after changing the skill.
- `README.md` explains FEN and the FEN/PGN distinction; keep those sections accurate when editing.
- Licensing: software and scripts are MIT (`LICENSE-MIT`); documentation and skill text are CC0-1.0 (`LICENSE-CC0`). Third-party model and library notices are in `THIRD_PARTY_NOTICES.md` and `LICENSES/2d-chess-ocr-MIT.txt`; keep them accurate when editing.
- `python-chess` is an optional GPL-3.0 dependency. Do not make it a hard requirement in `requirements.txt`; the built-in validator must work without it.
