---
description: 'Required pre-completion checks and PR review workflow for a Go project'
applyTo: "**"
---

# Pre-completion Checks

Before a task is marked as complete, all checks below must execute successfully
with no errors or warnings.

## Preferred: `make verify`

If the repository has a `verify` target, run it — it wraps the project's full
check sequence:

```bash
make verify
```

A typical `verify` target automates `go generate ./...`, `go build ./...`,
`go vet ./...`, `go test -race ./...`, and `shellcheck -o all` on shell scripts.
All steps must pass.

## Otherwise: run the sequence individually

When there is no `make verify`, run these in order. All must succeed:

1. **`go generate ./...`** — run first, *if the repo uses code generation*, so the
   steps below see the generated code.
2. **`go build ./...`** — all packages must compile (use `go build .` for a
   single-binary repo with only a root `main` package).
3. **`go fix ./...`** — apply any modernisations it offers.
4. **`go fmt ./...`** — all files must be formatted.
5. **`go vet ./...`** — must report no issues.
6. **`staticcheck ./...`** — must report no issues, *if the repo already uses it*
   (install: `go install honnef.co/go/tools/cmd/staticcheck@latest`).
7. **`go test -race ./...`** — all tests must pass with no data races.
8. **`shellcheck -o all <script.sh>`** — every shell script in the repo must pass.

# PR Review Workflow

## Finding the PR for the Current Branch

```bash
gh pr view --json number --jq .number
gh pr view
```

## Viewing Unresolved Review Comments

```bash
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
PR=$(gh pr view --json number --jq .number)

# View unresolved comments for the current PR
gh pr-review review view "$PR" --unresolved --repo "$REPO"

# Copy to clipboard (macOS)
gh pr-review review view "$PR" --unresolved --repo "$REPO" | pbcopy
```

## Workflow for Addressing Review Comments

1. Fetch unresolved comments for the current branch's PR
2. Analyze each comment to understand the feedback
3. Make code changes to address the issues
4. One commit per comment or related group of issues
5. Run the pre-completion checks (`make verify`, or the individual sequence)
6. Create a conventional commit with the fixes
7. Push the branch when all checks pass

## Commit Message Format for Review Fixes

```
fix: address PR {PR_NUMBER} review comments on {topic}

This commit addresses {N} unresolved review comments:

1. {Comment title} (line {X} of {file}.go)
   - {Description of fix}
```

See `git-workflow.instructions.md` for the attribution-trailer convention.
