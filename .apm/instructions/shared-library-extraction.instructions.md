---
description: 'When to promote a capability or bugfix into a shared dioad module instead of duplicating it locally'
applyTo: '**/*.go'
---

# Shared-Library Extraction Across dioad Repos

When a capability is needed in two or more `github.com/dioad` repositories,
or the same bug/gap is independently hit at two call sites — even within one
repo, if both go through a shared wrapper type — that recurrence is the
signal to promote the fix or capability into the appropriate shared module
rather than duplicating it locally. A second independent occurrence is the
trigger; do not extract speculatively on a single occurrence with no second
consumer in sight.

## Placement guide

| Capability | Home |
|---|---|
| Infra/HTTP/DNS/connection primitives | `dioad/net` |
| Identity, authz, claim/principal mapping | `dioad/auth` |
| Process/logging/CLI utilities shared across services | `dioad/cli` |
| Pub/sub client code | `dioad/eventbroker` (SDK) |

## Process

Extracting into a shared module is cross-repo work: follow
[cross-repo-workflow](./cross-repo-workflow.instructions.md) for editing,
verifying, committing, and publishing the change — edit the shared repo in
place via the local Go workspace, never with a `go.mod replace` directive,
and treat tagging/publishing the shared module as a user-triggered step.
