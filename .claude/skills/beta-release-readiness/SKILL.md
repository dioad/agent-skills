---
name: beta-release-readiness
description: >
  Activate when the user asks "is this ready for beta?", "can we ship this?",
  wants a go/no-go readiness check, or asks for a beta/production readiness
  checklist. Produces a single point-in-time verdict (Ready / Ready with
  caveats / Not ready) with a blocking-items checklist -- distinct from
  architecture-review, which produces an ongoing ranked findings backlog
  across eight lenses (one of which is this same readiness question, but
  folded into that longer-running list).
---

# Beta-Release Readiness

A single-pass go/no-go check for shipping a codebase, feature, or service to
early users. Unlike `architecture-review`, this is not a ranked backlog --
it is a checklist with a verdict, meant to be run right before a release
decision.

## When to activate

- User asks "is this ready for beta?" / "can we ship this?" / "are we ready
  to release?"
- User asks for a "readiness check", "release checklist", or "go/no-go"
- User references a beta, early-access, or soft-launch date and wants to know
  what's blocking it

## Relationship to architecture-review

`architecture-review` includes Beta-Release Readiness as one of its eight
lenses, for when readiness should be weighed against security, correctness,
etc. in one ranked list. Use *this* skill instead when the user wants a fast,
standalone answer to "can we ship?" without a full multi-dimension review.
If a `claude-review-architecture.md` already exists in the project, reuse
its Beta-Release Readiness findings as input rather than re-deriving them.

## Execution steps

1. Identify the release scope: whole codebase, a specific service, or a
   named feature. Ask if ambiguous.
2. Walk each checklist category below. For each item, mark it:
   - **Pass** -- meets the bar
   - **Gap (Blocking)** -- must be fixed before beta
   - **Gap (Non-blocking)** -- acceptable for beta, should be tracked
   - **N/A** -- doesn't apply to this scope
3. For every Gap, record: what's missing, why it matters at beta stage
   (not GA stage -- see calibration note below), and the concrete fix.
4. Produce the verdict and report it to the user directly (this is a
   point-in-time check, not a document meant to be filed away like
   `claude-review-architecture.md` -- only write it to a file if the user
   asks for one).

### Calibration: beta bar, not GA bar

Beta readiness is not production-hardened readiness. Judge against "safe to
put in front of real early users who know it's beta," not "safe at scale
with zero babysitting." Missing horizontal scaling, missing SLAs, or thin
docs for edge-case config are typically non-blocking at beta. Data loss,
silent failures, unrecoverable errors, exposed secrets, and no way to tell
if something broke are typically blocking at any stage.

## Checklist categories

- **Correctness of the core path** -- the primary user-facing flow works
  end-to-end; known crashes or data-corrupting bugs are blocking regardless
  of stage.
- **Error handling** -- failures are caught, surfaced, and don't leave the
  system in a broken or silently-wrong state. Errors reach a human or a log,
  not `/dev/null`.
- **Config & secrets** -- no hardcoded secrets or credentials; required
  config is documented; missing config fails loudly at startup, not deep in
  a request path.
- **Observability** -- enough logging/metrics to answer "is it working right
  now" and "what broke" without attaching a debugger. Structured logging
  conventions (if the project has them) are followed.
- **Test coverage of the critical path** -- the core flow has automated
  tests; a regression there would be caught before a user hits it.
  Exhaustive coverage of edge cases is not required for beta.
- **Documentation for the beta audience** -- setup/usage instructions exist
  for whoever is trying the beta (internal team, design partners, public
  signup). Internal architecture docs are not required for beta.
- **Rollback / kill switch** -- there is a known, fast way to disable the
  feature or revert the release if it goes wrong.
- **Known-gaps disclosure** -- anything intentionally deferred past beta is
  written down somewhere the team can see, not just in someone's head.

## Output format

Report directly to the user (or write to a file only if asked):

```
# Beta Readiness: <scope>

**Verdict:** Ready | Ready with caveats | Not ready
**Reviewed:** YYYY-MM-DD

## Blocking gaps
1. <item> -- <why it blocks beta> -- <concrete fix>
...

## Non-blocking gaps (track, don't block)
1. <item> -- <recommended follow-up>
...

## Pass
- <category>: <one-line confirmation>
...
```

## Constraints

- Do not fix the gaps yourself unless the user asks -- this skill reports
  the verdict, it doesn't remediate.
- Do not apply GA/production-scale bar by default; calibrate to beta per the
  note above unless the user says otherwise.
- Do not duplicate a full architecture-review -- if the user actually wants
  the eight-lens ranked findings document, redirect to `architecture-review`.
