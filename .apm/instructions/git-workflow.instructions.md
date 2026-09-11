---
description: 'Git workflow rules for this repository'
applyTo: "**"
---

# Git workflow instructions

When performing Git operations in this repository, follow these rules:

1. Never push to remote repositories (`git push` is not allowed).
2. Do not use `git add -A` (or `git add .`). Stage files explicitly by path.
3. Only stage files you directly modified for the requested task.
4. Use Conventional Commits for commit messages (for example: `fix: ...`, `feat: ...`, `chore: ...`).
5. If the agent tooling appends an attribution trailer (e.g. `Co-Authored-By: <model> <noreply@anthropic.com>`), let it use whatever the current session reports as the model name. Never hardcode a specific model name/version into a committed template or instruction file — it goes stale the moment a newer model ships.

Recommended safety practices:

1. Do not create commits unless the user explicitly asks for a commit.
2. Do not amend commits unless explicitly requested.
3. Before committing, inspect staged changes with `git diff --cached` to confirm scope is correct.
