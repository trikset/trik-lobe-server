# Copilot / code-review instructions for trik-lobe-server

The `github-code-quality` reviewer must respect this project's enforced
quality gates and the rules in `AGENTS.md`. Only suggest changes that keep
every gate green.

## Enforced gates (CI runs all of these)

- **100% test coverage** — `source = ["lobe_server"]`, `fail_under = 100`.
  Test-only code is not covered, so it is exempt.
- **ruff** `select = ["ALL"]` — production linting at full strictness.
- **basedpyright strict** — 0 errors.
- **pylint** 10.00, **bandit**, **vulture** clean.

## Protocol and abstract stubs

A bare `...` (ellipsis) is the correct and intentional stub body for
`Protocol` methods and abstract methods in this codebase:

- coverage.py treats a `...` stub line as excluded by design, which is how
  100% coverage is maintained for never-called interface stubs.
- Replacing `...` with `pass` breaks basedpyright's return-type check
  ("must return value on all code paths").
- Replacing `...` with `raise NotImplementedError` would be counted as
  uncovered code and drop coverage below 100%.

Therefore **do not flag `...` in Protocol/abstract stub bodies as "statement
has no effect"** — it is required by the project's toolchain.

## Review guidance

- Prefer idiomatic, minimal diffs; keep SLOC and complexity low.
- Respect the suppression policy in AGENTS.md: every in-code suppression
  (`# noqa`, `# type: ignore`, `# pylint: disable`, `# nosec`) is either
  scoped to tests or carries a reasoning comment.
- Do not suggest new dependencies or tool-config changes unless they keep
  all gates green.
