---
name: release-notes
description: Generate end-user-friendly release notes for a GitHub release. Use when creating a release or tagging vYY.MM.DD. Produces a simple-English user summary (Part 1) plus a developer changelog (Part 2) with an updated dependencies table, major issues, contributors, and a compare link.
---

# Release notes generator

Generate release notes for the tag being released. Work ONLY on this task.

## Scope guard (hard rule)

- Write ONLY to `release-notes.md` in the repository root.
- Do NOT modify any code, CI workflow, config, or documentation file.
- Do NOT create, edit, or publish a GitHub release. The CI workflow creates
  the draft; the maintainer reviews and publishes it.
- Do NOT run git commands that change state (no commits, tags, pushes).

## Steps

1. Determine the tag being released and the previous release tag. Both are
   passed as arguments: the current tag and the previous release tag. If the
   previous tag is not given, find it:
   `gh release list --limit 10 --json tagName --jq '.[].tagName'` (or
   `git tag --list 'v*' --sort=-version:refname`). If none exists, use the
   earliest PR in the list as the starting point.
1. Collect merged pull requests since the previous release:
   `gh pr list --state merged --base main --limit 100 --json number,title,mergedAt,author`
   Filter to PRs merged after the previous release. Keep newest-first order.
1. Run the PROMPT below with that PR list, then write the result to
   `release-notes.md`.

## PROMPT

You are writing the release notes for "TRIK Lobe Server". This is a desktop
application that lets a user run AI image-recognition models (ONNX or TFLite)
on their PC, detect objects from a camera, and send the result over TCP to a
TRIK robot or TRIK Studio. The main audience is school teachers and TRIK
robotics enthusiasts who want their robots to "see" and react. Many are not
programmers.

Write release notes in SIMPLE ENGLISH. Use short sentences, common words, and
no jargon. Structure them in two clearly separated parts:

PART 1 — End-user summary (warm, simple, non-technical):

- A short 2-4 sentence paragraph titled "What's new" describing, in plain
  everyday language, what this release brings to a teacher who just wants to
  make their robot recognize objects. Focus on real user value: reliability,
  camera support, model compatibility, ease of use.
- Then a short bulleted list "Key improvements" (3-6 bullets) of the most
  user-visible improvements, each in one plain sentence. NO jargon like
  "backend", "refactor", "CI", "lint", "dependency", "lockfile".

PART 2 — Developer reference, in this order:

1. Heading "For developers".
1. A heading "### Updated dependencies" with a markdown table of every
   dependency that changed since the previous release. Columns: `Dependency`
   and `Version`. Use the version reached in this release (e.g. `onnxruntime`
   | `1.28`). One row per dependency. If nothing changed, omit this section.
   Do NOT list dependency bumps as bullets anywhere.
1. A heading "### Major changes" with a bullet list of only significant
   commits: features, fixes, large PRs, and major improvements. In
   Conventional Commits style: `- fix: short description (#123)`. Drop routine
   `chore(deps)`, `docs`, `ci`, and other internal bumps — they belong in the
   dependencies table or the compare link, not here.
1. A "Contributors" line listing the human authors of the merged PRs. Remove
   obvious bots (dependabot, github-actions, renovate, etc.). Format as
   `Contributors: [@username](https://github.com/username), ...`. Mark new
   contributors (first PR in this repository) in bold with `(new)`:
   `**@username (new)**`.
1. The last line, exactly:
   `Detailed comparison with previous release vX.YY.ZZ: <https://github.com/trikset/trik-lobe-server/compare/vX.YY.ZZ...vCURRENT>`
   using the actual previous tag and current tag.

RULES:

- Part 1 must be genuinely user-facing: talk about what the user can now DO,
  what got faster/more reliable, what new model or camera formats are
  supported. Do NOT translate developer terms — rephrase them into plain
  words.
- Part 1 must NOT mention: PR numbers, CI, linters, dependency versions,
  lockfiles, copyright headers, Dependabot, model internals.
- Part 1 should mention (when true for the release): recognition runs locally
  on the PC (no internet needed), and models trained in Lobe work out of the
  box. Refer to model files as "the model files Lobe can save" instead of
  naming ONNX/TFLite.
- Keep Part 1 concise and friendly. Part 2 is the developer log.
- Separate the two parts with a `---` divider.

INPUT — merged changes for this release (Conventional-Commits-style titles,
newest first), with author login per PR:
<insert the PR list here>

Current tag: <current tag>
Previous release tag: <previous tag>
