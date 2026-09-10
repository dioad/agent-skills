---
description: 'Rules for working across sibling github.com/dioad repositories via the local Go workspace'
applyTo: "**"
---

# Cross-Repository Workflow

`connect` is developed alongside sibling `github.com/dioad` repositories
(`auth`, `net`, `cli`, `eventbroker`, `connect-control`, and others) that are
linked locally through a Go workspace file (`go.work`) one directory above
`connect`. Not every sibling repo is active in that workspace's `use` list at
all times — some entries are commented out. Before assuming workspace
resolution applies to a given sibling, confirm it is actually enabled there;
if it isn't and the task needs it, tell the user and ask before adding it —
enabling a repo in the shared workspace changes what every session across
every dioad repo resolves against, so it is not a decision to make silently.

## Never use `go.mod replace` directives

Do not add a `replace` directive to pull in a local sibling module. The Go
workspace already provides this. A `replace` directive masks version drift
between what `go.mod` declares and what's actually being built against, and
it is easy to forget to remove before a real release build.

## Editing a sibling repo

When a fix or change belongs in a sibling repo:

1. Edit it in place in that repo's own directory.
2. Run that repo's own verification (its own `make verify` or equivalent) —
   do not rely on `connect`'s checks to validate a sibling repo's code.
3. Commit inside that repo, separately from any `connect` commit. Do not
   fold a sibling repo's changes into a `connect` commit.

## Publishing and version bumps are user-triggered

Never tag/publish a new version of a shared module, and never bump a
consuming repo's `go.mod` to point at a new release. Implement and commit
the change locally in the sibling repo, then stop and report that a version
bump is needed — do not do it unprompted. Resume only once the user confirms
the bump (e.g. "I've bumped `dioad/net`, please carry on and commit").

## Deferred fixes: file an upstream issue

If the correct fix for something found during this session's work belongs in
a sibling repo but is out of scope right now, don't leave it as a dangling
note in a review document or commit message. File a GitHub issue in the
target repo:

```bash
gh issue create --repo github.com/dioad/<repo> --title "..." --body "..."
```

Give the issue enough context that a fresh session — human or agent — can
pick it up without needing this conversation's history.
