---
description: "Measure Go test-suite strength (mutation testing + per-test coverage contribution), then work the findings one commit at a time"
argument-hint: "[measure [--scope PKG] [--delta] [--per-test PKG] | address [A|B|C|D]]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "Task"]
---

# Test Quality Workflow

Measure how well a Go project is tested and produce LLM-actionable findings, or
work through findings from a prior run.

**Arguments:** "$ARGUMENTS"

The `test-quality` skill carries the full procedure. Load it and follow it. The
two helper scripts (`measure.sh`, `test_quality.py`) ship in the skill directory;
`measure.sh` locates the target repo with `git rev-parse --show-toplevel`, so it
runs from anywhere.

---

## Phase 1: Measure (`test-quality measure [...]`)

Run `measure.sh` from the skill directory with any of `--scope ./tree/...`,
`--delta` (only lines changed vs `master`), and `--per-test PKG` (repeatable;
adds the contribution map and covering-test lines for that package).

It writes three artifacts against the repo under test:

- `.analysis/test-quality/scorecard.md` — statement coverage, mutation coverage,
  and test efficacy as a **vector, never blended** (they move independently; the
  divergence is the signal). `NOT VIABLE` excluded from all denominators;
  `TIMED OUT` policy stated in the output.
- `.analysis/test-quality/contribution.md` — per-test contribution, greedy
  minimal set, and `REVIEW` (consolidation-candidate) tests.
- `doc/test-quality-findings.md` — sections A (weak assertions), B (coverage
  gaps), C (redundancy — expect most to be keeps), D (risk).

Report back: the three headline numbers, the weakest packages by efficacy, and
the A/B/C counts.

---

## Phase 2: Address (`test-quality address [A|B|C|D]`)

Work `doc/test-quality-findings.md` top-down, one conventional commit per finding
group.

- **A / B** — add or tighten one assertion (A) or add a test that reaches the
  listed lines (B). **Verify each fix with the mutation round-trip** the finding
  names: `gomutants -run-mutant-id '<id>' -o /tmp/gomutants-verify.json ./<pkg>`
  must flip `LIVED → KILLED`. Do not commit a fix that did not flip.
- **C** — read each REVIEW test. Keep it if it names a behaviour no sibling
  names; only fold-and-delete a genuine near-duplicate, stating the reason. Skip
  log-only surviving mutants.
- **D** — prioritisation input only; no separate commits.

Run the target repo's pre-completion checks before every commit. Do not push.
