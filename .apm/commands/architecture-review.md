---
description: "Comprehensive architecture review across eight lenses, then work the ranked findings one commit at a time"
argument-hint: "[review | address [High|Medium|Low]]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "Task"]
---

# Architecture Review Workflow

Generate a ranked architecture-review findings document, or work through the
findings from a prior run.

**Arguments:** "$ARGUMENTS"

The `architecture-review` skill carries the full procedure. Load it and follow
it.

---

## Phase 1: Review (`architecture-review review`)

Review the codebase across eight lenses — Good Engineering Practices,
Correctness, Operability, Documentation, Security, Hexagonal Architecture, Low
Coupling/Complexity, and Beta-Release Readiness — and write open findings to
`doc/claude-review-architecture.md` (create `doc/` if absent).

Each finding records file(s), dimension(s), a description, a concrete fix, and a
High/Medium/Low priority. Report back the total count and the top three
High-priority items.

---

## Phase 2: Address (`architecture-review address [High|Medium|Low]`)

Work `doc/claude-review-architecture.md` in priority order (or only the
priority named in the argument), one conventional commit per finding — with the
sole exception of a finding needing a structural refactor, which splits into a
zero-behavior extraction commit plus a behavior-change commit under the
phased-refactor pattern.

Per finding: baseline `gocognit <file>`, make the minimal fix, run the target
repo's pre-completion checks (`make verify` or its `project-checks` sequence),
re-check `gocognit` (complexity must not rise unless the readable form requires
it), commit `fix: <finding title>`, then move the finding to
`doc/claude-review-architecture-resolved.md` with its commit SHA and
complexity delta. Do not push.
