---
description: 'Two-phase methodology for structural refactors: make the change easy, then make the easy change'
applyTo: '**/*.go'
---

# Phased Refactors: Make the Change Easy, Then Make the Easy Change

Kent Beck's formulation: "for each desired change, make the change easy
(warning: this may be hard), then make the easy change." Apply this whenever
a change requires restructuring code — splitting a type, extracting an
interface, decomposing a large function or struct, moving a package — before
or alongside a behavior change.

## Steps

1. **Characterize current behavior first.** If the area being refactored
   lacks a test that pins down its current behavior, write one before
   touching production code.

2. **Phase 1 — make the change easy.** Do the structural extraction, split,
   or move as its own commit with zero behavior change. The existing (or
   newly added characterization) test suite must pass unmodified. If a test
   has to change to make this commit pass, the extraction changed behavior
   and is not ready to be treated as "just structure."

3. **Phase 2 — make the easy change.** With the structure in place, make the
   actual behavior change as a separate, now-mechanical commit.

## Signal to watch for

If Phase 1's commit has to duplicate meaningful logic instead of moving it,
that's a sign the wrong seam was chosen. Reconsider what to extract before
continuing to Phase 2 rather than pushing through with the duplication.

## Relationship to the architecture-review skill

A single review finding may legitimately need two commits under this
pattern — an extraction commit and a behavior-change commit — rather than
one. That is compatible with, not a violation of, the "one commit per
finding" workflow: both commits address the same finding, so they are not
"unrelated findings" being batched together.
