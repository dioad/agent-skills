---
description: "Single-pass go/no-go readiness check for shipping to early users — verdict plus a blocking-items checklist"
argument-hint: "[scope: whole repo | a service | a named feature]"
allowed-tools: ["Bash", "Glob", "Grep", "Read"]
---

# Beta-Release Readiness Check

Answer "can we ship this to beta?" with a point-in-time verdict and a
blocking-items checklist. This is not a ranked backlog — for the eight-lens
review use `architecture-review` instead.

**Arguments:** "$ARGUMENTS"

The `beta-release-readiness` skill carries the full procedure. Load it and
follow it.

Walk each checklist category — core-path correctness, error handling, config &
secrets, observability, critical-path test coverage, beta-audience docs,
rollback/kill switch, known-gaps disclosure — marking every item Pass, Gap
(Blocking), Gap (Non-blocking), or N/A. Calibrate to the beta bar ("safe in
front of real early users who know it's beta"), not the GA bar. If a
`claude-review-architecture.md` already exists, reuse its Beta-Release Readiness
findings as input.

Report the verdict (Ready / Ready with caveats / Not ready) directly to the
user — only write it to a file if asked. Do not remediate the gaps unless the
user asks.
