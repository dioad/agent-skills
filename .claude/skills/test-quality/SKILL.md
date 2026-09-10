---
name: test-quality
description: >
  Activate when the user wants to measure how well a Go project is tested, find
  weak spots in the test suite, or act on a prior test-quality report. Combines
  mutation testing (gomutants) with per-test coverage-contribution analysis to
  produce a quantitative scorecard, a test contribution map (redundancy /
  consolidation candidates via greedy set-cover), and an LLM-actionable findings
  doc (doc/test-quality-findings.md) covering weak assertions, coverage gaps and
  risk. Phase 2 works through findings one commit at a time.
---

# Test Quality

A two-phase skill. **Phase 1** measures the suite and writes three artifacts.
**Phase 2** works through the findings one conventional commit at a time,
verifying each fix with a mutation round-trip.

## When to activate

- "How well tested is this?", "score our test suite", "test quality report"
- "Where are the tests weak?", "which assertions are missing?"
- "Which tests are redundant / can we delete?", "consolidate the tests"
- "Address the test-quality findings", references `doc/test-quality-findings.md`

## Determine the phase

- **Phase 1** — generate a report. Keywords: "measure", "score", "report",
  "analyse the tests", "test-quality review".
- **Phase 2** — act on an existing report. Keywords: "address", "fix findings",
  "work through", "strengthen the assertions", "retire redundant tests".

If unclear, ask which.

## Tooling

`gomutants`, `go`, and `python3` (3.11+) must be on `PATH`. `gocognit` is
optional (adds the risk section). Two files ship beside this `SKILL.md`:

- `measure.sh` — orchestrator; runs the measurements and renders the artifacts.
  It resolves the target repo with `git rev-parse --show-toplevel`, so it works
  from any working directory and does not care where the skill is installed.
- `test_quality.py` — report generator (`scorecard` / `findings` /
  `contribution` sub-commands). Does no measurement itself.

Below, `$SKILL` is the directory this `SKILL.md` lives in — `.claude/skills/test-quality`
in a project that installed the skill, or `~/.claude/skills/test-quality` for a
user-level install. Run the target repo's own pre-completion checks, not this
package's.

All raw output and the scorecard land under `.analysis/test-quality/` of the
repo under test. The findings doc lands in that repo's `doc/`.

---

## Phase 1: Measure

### Run it

```bash
# full run over ./internal/... (~15-20 min; incremental cache makes reruns fast)
"$SKILL/measure.sh"

# a different tree
"$SKILL/measure.sh" --scope ./sdk/...

# fast delta run -- only mutants on lines changed vs master
"$SKILL/measure.sh" --delta

# add the test contribution map for one or more packages (redundancy analysis)
"$SKILL/measure.sh" \
  --per-test ./internal/cmd/entitlements/service \
  --per-test ./internal/cmd/accounting/service
```

`--per-test PKG` runs one coverage profile per test in that package and builds
the contribution map. Without it, Section C (redundancy) and the contribution
map are skipped, **and Section A/B findings for that package have no "Covering
tests" line**. Pass `--per-test` once per package, and always pass it for the
package you intend to work on in Phase 2.

When `--per-test` and the mutation report are both present, the contribution map
also gets a **Sole-kill** column: killed mutants whose source line no other
test's coverage reaches, so that test is the only possible killer. This is a
mutation-informed uniqueness signal derived from data already on disk — gomutants
does not expose which test killed each mutant, and blocks the `-run` override
that would let the skill find out, so true per-test kill sets are not available.

### The three artifacts

| File | Purpose |
|---|---|
| `.analysis/test-quality/scorecard.md` | quantitative vector + per-package table |
| `.analysis/test-quality/contribution.md` (+ `.json`) | per-test contribution, greedy minimal set, redundancy candidates |
| `doc/test-quality-findings.md` | LLM-actionable: weak assertions (A), coverage gaps (B), redundancy (C), risk (D) |
| `.analysis/test-quality/mutation-report.html` | interactive mutant browser |

### Reading the score — do not blend the numbers

Three headline metrics that **move independently**:

| Metric | Means | A rise means |
|---|---|---|
| Statement coverage | how much code the suite executes | more code reached |
| Mutation coverage | reach at mutant granularity | more mutable behaviour reached |
| **Test efficacy** (headline) | kill rate where tests *do* reach | assertions actually pin behaviour |

Adding a test that runs code without asserting on it **raises mutation coverage
and lowers efficacy**. That divergence is the point. There is deliberately no
single "test quality number".

Conventions the scorecard states explicitly:

- `NOT VIABLE` mutants (won't compile) are excluded from every denominator.
- `TIMED OUT` is ambiguous; default policy is `exclude` (out of the efficacy
  denominator). Override with `--timeout-policy kill|survive` if the user wants
  the gremlins convention (`kill`).

### Report back

After a run, tell the user: the three headline numbers, the 3 weakest packages
by efficacy from the scorecard, the count of Section A / B / C findings, and the
count of REVIEW-flagged tests from the contribution map.

---

## Phase 2: Act on findings

Work `doc/test-quality-findings.md` top-down. Sections A, B and D are additive
(new or stronger tests). Section C is subtractive and needs judgement.

### Section A — weak assertions (one commit per finding group)

For each `### An.` group, ranked by weighted survivor count:

1. **Read** the source context and the covering tests named in the finding.
2. **Add or tighten one assertion** so a covering test observes an output or
   error that the listed mutations would change. Prefer asserting on the
   function's return value / emitted event / persisted state — not on logging.
   - Surviving `STATEMENT_REMOVE` / `BRANCH_IF` on a pure logging line is often
     **not worth a test**. Note it as accepted and move on; do not contort a
     test to kill a log-only mutant.
3. **Verify the round-trip** — this skips the incremental cache:
   ```bash
   gomutants -run-mutant-id '<id from the finding table>' \
     -o /tmp/gomutants-verify.json ./<package>
   ```
   The mutant must flip `LIVED → KILLED`. If it does not, the assertion is not
   pinning the mutated behaviour — rework it before committing.
4. **Pre-completion checks** — run the target repo's own gate (e.g. a
   `project-checks` rule or `make verify`); a common Go baseline is:
   ```bash
   go fix ./...  && go fmt ./...  && go vet ./...  && go test -race ./...  && go build .
   ```
5. **Commit** — one conventional commit per finding group:
   `test(<pkg>): assert <behaviour> in <Func>`

### Section B — coverage gaps

Same workflow, but step 2 is "write a new test that calls the function with
inputs that reach the listed lines". Verify with the same round-trip on one of
the previously `NOT COVERED` mutants (it should move to `KILLED`).

### Section C — redundancy & consolidation candidates

Each REVIEW test has **no unique coverage block**, no solely-reached killed
mutant, and is not required by the greedy set-cover. This is a prompt, never a
delete order — **expect most REVIEW entries to be keeps**. Coverage overlap is
not behavioural overlap: a test that names a distinct branch, error path, or
contract is unique evidence even at zero unique blocks. For each:

1. **Read the test.** Ask: does its name and body document an externally
   meaningful behaviour or business rule that no sibling test names?
   - **Yes** → keep it. Record in the commit body why (semantic value).
   - **No — it is a near-duplicate** of a named sibling → fold any assertion it
     has that the sibling lacks into the sibling, then delete the REVIEW test.
2. After removing candidates, **re-run** `"$SKILL/measure.sh" --per-test PKG`
   for that package. The minimal-set size and efficacy must not drop. If
   efficacy fell, the deleted test carried a unique kill the coverage proxy
   missed — restore it.
3. **Commit** — `test(<pkg>): consolidate <TestX> into <TestY>` or
   `test(<pkg>): remove redundant <TestX>`, one commit per removal or tight
   group.

### Section D — risk

High cognitive complexity plus surviving/uncovered mutants. No separate action —
use it to prioritise which Section A/B items to do first, and consider whether
the function itself should be split (a `positive design pressure` signal).

### Constraints

- One finding group per commit; never batch unrelated groups.
- Never commit a Section A/B fix whose mutation round-trip did not flip.
- Never delete a Section C test without reading it and stating the reason.
- Do not push. Local commits only.
- Re-run `"$SKILL/measure.sh"` (or `--delta`) at the end and report the
  efficacy delta.
