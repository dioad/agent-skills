---
name: architecture-review
description: >
  Activate when the user asks for a comprehensive architecture review of the
  codebase, or wants to systematically address findings from a prior review.
  Reviews across eight lenses -- good engineering practices, correctness,
  operability, documentation, security, hexagonal architecture, low
  coupling/complexity, and beta-release readiness. Generates a ranked
  findings document (doc/claude-review-architecture.md) or works through
  existing findings one commit at a time.
---

# Architecture Review

A two-phase skill for reviewing and improving codebase architecture. Phase 1
generates a ranked findings document; Phase 2 addresses findings
systematically, one commit at a time.

## When to activate

- User asks for an "architecture review" or "code review"
- User asks to "review the codebase" or "find architectural issues"
- User asks to "address findings" from a prior architecture review
- User references `claude-review-architecture.md`
- User says "architecture-review review" or "architecture-review address"

## Determine the phase

Examine the user's request to determine which phase to run:

- **Phase 1** — the user wants a new review generated. Keywords: "review",
  "analyse", "generate findings", "what's wrong with", "architecture-review review".
- **Phase 2** — the user wants to act on existing findings. Keywords: "address",
  "fix findings", "work through", "architecture-review address".

If unclear, ask: "Do you want to generate a new architecture review, or address
findings from an existing one?"

## Document locations

Architecture review documents live in the project's `doc/` directory (create
it if it doesn't exist yet). This is the fixed convention across this
package's skills — `test-quality` writes its findings to `doc/` too, with no
`docs/` fallback — so pick `doc/` even if the project already has a `docs/`
directory.

The two files are:

- **`doc/claude-review-architecture.md`** — open (unresolved) findings.
- **`doc/claude-review-architecture-resolved.md`** — resolved findings,
  with commit SHA and outcome for each.

---

## Phase 1: Generate Review

Perform a comprehensive architecture and engineering review of the current
codebase and write open findings to `doc/claude-review-architecture.md`.

### Review dimensions

Analyse the codebase across these eight lenses:

- **Good Engineering Practices** -- alignment with current language idioms
  and community standards; mismatched patterns, duplicate logic, and
  divergent conventions across packages or files
- **Correctness** -- bugs, race conditions, error handling gaps, incorrect
  assumptions
- **Operability** -- observability (structured logging, metrics, tracing),
  configuration management, graceful shutdown, health checks, failure-mode
  handling, resource cleanup, and deployability
- **Documentation** -- package and exported-symbol docs, README/setup
  instructions, runnable examples, and comments that explain non-obvious
  "why" rather than restating "what"
- **Security** -- trust boundaries, authn/authz, secret handling, input
  validation, TLS/crypto usage, and dependency exposure. This is a
  codebase-wide lens distinct from the diff-scoped `security-review` skill;
  it does not replace running that skill on a pending change.
- **Hexagonal Architecture** -- separation of domain logic from
  infrastructure (ports/adapters), direction of dependencies, and candidates
  for restructuring toward clearer boundaries
- **Low Coupling / Complexity** -- coupling, cohesion, cyclomatic/cognitive
  complexity, testability
- **Beta-Release Readiness** -- go/no-go signal for shipping to early users:
  gaps in error handling, config/secrets management, test coverage,
  documentation, and observability that would block or risk a beta release

### Execution steps

1. Read the project's entry points, core packages, and test files to build a
   mental model of the system.
2. Analyse each dimension in turn. For each finding, record:
   - Which file(s) are affected
   - Which dimension(s) it falls under
   - A clear description of the problem
   - A concrete recommended fix
   - A priority rating: **High**, **Medium**, or **Low**
3. Write all findings to `doc/claude-review-architecture.md` using the
   output format below.
4. After writing, report the total finding count and top three High-priority
   items to the user.

### Output format

Write `doc/claude-review-architecture.md` with this structure:

```
# Architecture Review: `<module-path>`

_Reviewed: YYYY-MM-DD — branch `<branch>` (<commit-sha>)_

---

## Executive Summary
<2-4 sentences: overall health, most critical theme, recommended focus>

---

## Findings

### N. <Finding Title>

- **File(s):** <path(s)>
- **Dimension(s):** <one or more of: Good Engineering Practices, Correctness, Operability, Documentation, Security, Hexagonal Architecture, Low Coupling/Complexity, Beta-Release Readiness>
- **Priority:** High | Medium | Low
- **Status:** Open
- **Description:** <what the problem is and why it matters>
- **Recommended fix:** <concrete, actionable steps>

... (repeat for each finding)

---

## Priority Table

| # | Priority | Status | Finding | File(s) |
|---|----------|--------|---------|---------|
| 1 | High     | Open   | ...     | ...     |
| 2 | Medium   | Open   | ...     | ...     |
| 3 | Low      | Open   | ...     | ...     |
```

`<module-path>` is the repo's Go module path (from `go.mod`), e.g.
`github.com/dioad/<repo>`.

---

## Phase 2: Address Findings

Work through findings in `doc/claude-review-architecture.md` one at a
time. Each finding gets exactly one conventional commit — except a finding
that requires a structural refactor (splitting a type, extracting an
interface, moving a package), which follows the phased-refactor pattern
instead (see `phased-refactor.instructions.md`, distributed alongside this
skill, for the full methodology): a zero-behavior-change extraction commit,
then a behavior-change commit, both addressing the same finding.

### Scope

If the user specifies a priority (e.g. "High only"), process only findings
at that priority. Otherwise process all unresolved findings in priority order
(High first).

### Per-finding workflow

For each finding:

1. **Plan** -- read the finding and identify the minimal correct fix.

2. **Baseline complexity** -- before touching any file, record its cognitive
   complexity:
   ```bash
   gocognit <file>
   ```

3. **Fix** -- implement the change.
   - If the correct fix belongs in a sibling module that is part of the
     local `go.work` workspace and is in scope for this session, edit it in
     place -- never add a `replace` directive to `go.mod`. Verify and commit
     inside that sibling repo separately.
   - If the correct fix belongs upstream but is out of scope right now,
     create a GitHub issue instead of a local change:
     ```bash
     gh issue create --repo <owner>/<repo> --title "..." --body "..."
     ```

4. **Verify** -- run the target repo's own pre-completion checks before
   committing. Prefer `make verify` if the repo has that target; otherwise
   follow the repo's `project-checks` rule (see `project-checks.instructions.md`,
   distributed alongside this skill, if the target repo carries it). If neither
   is available, run this baseline in order and require every step to pass:
   ```bash
   go generate ./...   # only if the repo uses code generation
   go build ./...       # go build . for a single-binary repo with only a root main
   go fix ./...
   go fmt ./...
   go vet ./...
   go test -race ./...
   ```
   Do not proceed to the commit step if any check fails.

5. **Post-fix complexity** -- record cognitive complexity after the fix:
   ```bash
   gocognit <file>
   ```
   The complexity score must stay the same or decrease. If it increases,
   rethink the approach -- unless the only way to avoid the increase is to
   game the metric at the cost of human readability (e.g. an artificial split
   that reads worse than the unsplit version). In that case, keep the
   readable version: record the finding as resolved with a note that the
   complexity delta was knowingly accepted and why, rather than forcing an
   unreadable split.

   Repo-wide target (informational, used to prioritise which complexity
   findings to pick up first -- not a hard per-finding gate): no more than
   1-2 functions with cyclomatic complexity over 15, and fewer than 5
   functions with cognitive complexity over 15.

6. **Commit** -- one conventional commit per finding:
   ```
   fix: <short description matching the finding title>
   ```

7. **Update documents** -- move the finding from the open file to the
   resolved file:
   - Remove it from `doc/claude-review-architecture.md` and update the
     Priority Table.
   - Append it to `doc/claude-review-architecture-resolved.md` in the
     resolved format:
     ```
     ### N. <Finding Title> ✅ Resolved

     - **File(s):** <path(s)>
     - **Dimension(s):** <dimension(s)>
     - **Priority:** High | Medium | Low
     - **Resolved in:** <commit-sha>
     - **Complexity delta:** <before> -> <after>
     - **Description:** <original description>
     - **Outcome:** <what was changed, and why any complexity increase was accepted>
     ```

### Constraints

- Do not batch multiple unrelated findings into a single commit (a phased
  structural refactor for one finding is not "unrelated" -- see above).
- Do not skip the pre-completion checks step.
- Do not let complexity increase after a fix, unless avoiding the increase
  would require gaming the metric at the cost of readability -- in that case,
  keep the readable version and record why the complexity delta was accepted.
- Do not push to remote; committing locally is sufficient.
