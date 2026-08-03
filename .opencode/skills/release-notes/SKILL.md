______________________________________________________________________

## name: release-notes description: Generate end-user-friendly release notes for a GitHub release. Use when creating a release or tagging vYY.MM.DD. Produces a simple-English user summary (Part 1) plus a developer changelog (Part 2).

# Release notes generator

Generate release notes for the tag being released. Work ONLY on this task.

## Scope guard (hard rule)

- Write ONLY to `release-notes.md` in the repository root.
- Do NOT modify any code, CI workflow, config, or documentation file.
- Do NOT create, edit, or publish a GitHub release. The CI workflow creates
  the draft; the maintainer reviews and publishes it.
- Do NOT run git commands that change state (no commits, tags, pushes).

## Steps

1. Determine the tag being released. It is passed as the argument, or read the
   current git tag if unambiguous.
1. Find the previous release tag:
   `gh release list --limit 10 --json tagName --jq '.[].tagName'` (or `git tag --list 'v*' --sort=-version:refname`). If none exists, use the earliest PR in the list as the starting point.
1. Collect merged pull requests since that tag:
   `gh pr list --state merged --base main --limit 100 --json number,title,mergedAt`
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

PART 2 — Developer reference (conventional GitHub style):

- A heading "For developers" followed by a bullet list, one line per change,
  in Conventional Commits style: `- fix: short description (#123)`. Keep the
  same order as input. Include ALL input items here, even internal ones
  (docs, CI, deps).

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
- Keep Part 1 concise and friendly. Part 2 is the exhaustive developer log.
- Separate the two parts with a `---` divider.

INPUT — merged changes for this release (Conventional-Commits-style titles,
newest first):
<insert the PR list here>
