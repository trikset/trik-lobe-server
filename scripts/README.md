# Scripts

Developer-oriented tools for CI, quality gates, screenshots, and demos.

| Script | Purpose | Run |
|--------|---------|-----|
| `gate.py` | Quality gate: runs ruff, basedpyright, pylint, bandit, vulture, pytest | `uv run python3 scripts/gate.py` |
| `check-pr.sh` | Pre-PR readiness check (branch, .omo/ artifacts, rebase status) | `bash scripts/check-pr.sh` |
| `log.sh` | Wrapper: runs a command and tees full output to `.tmp/<name>.log` | `bash scripts/log.sh <cmd>` |
| `pre-commit-main-block` | Git hook: rejects commits on `main` branch | Symlink to `.git/hooks/pre-commit` |
| `pre-push` | Git hook: blocks pushes to `main`, tag deletion, .omo/ in commits | Symlink via `bash scripts/install-hooks.sh` |
| `install-hooks.sh` | Install git hooks (pre-push) | `bash scripts/install-hooks.sh` |
| `gen-demo.py` | Generate `.ansi` files for screenshot pipeline | `uv run scripts/gen-demo.py` |
| `render-screenshots.py` | Render `.ansi` → `.png` with ANSI colour parsing | `uv run scripts/render-screenshots.py` |

## Screenshot pipeline

```bash
# One-shot (regenerates screenshots-light.png and screenshots-dark.png)
uv run scripts/gen-demo.py
uv run scripts/render-screenshots.py .tmp/demo-dark.ansi screenshots-dark.png --dark
uv run scripts/render-screenshots.py .tmp/demo-light.ansi screenshots-light.png
```

The pipeline is documented in `MEMORY.md` ([2026-10-12] btop-style multi-zone
dashboard, Screenshot generation dependency). When the panel output format
changes (cursor-up sequence, box-drawing characters, line count), both
`gen-demo.py` and `render-screenshots.py` must be updated.

## Live demo

The standalone demo dashboard lives in the main app (`--demo` mode) with
fake fruit predictions — no camera, model or robot connection:

```bash
uv run python TRIKMind.py --demo            # ~16fps pipeline, until Ctrl+C
uv run python TRIKMind.py --demo --fps 5    # slower: 1 detection per second
```

`--fps N` simulates a pipeline running at N frames/sec; a detection is
emitted once per 5 frames, so events arrive at N/5 per second (fps=16 →
≈3.2 events/sec). The dashboard's fps counter reads ≈N. The fake prediction
source is `trik_mind/demo.py` (`DemoSource`).
