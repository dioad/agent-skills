# agent-skills

Shared agent skills, commands, and instructions for dioad Go projects,
distributed as an [APM](https://microsoft.github.io/apm) package. Each skill also
works standalone — copy its directory into any `.claude/skills/`.

## Contents

| Skill | What it does |
|---|---|
| [`architecture-review`](.apm/skills/architecture-review/SKILL.md) | Review the codebase across eight lenses (good engineering practices, correctness, operability, documentation, security, hexagonal architecture, low coupling/complexity, beta-release readiness); emit a ranked findings document, then work through it one conventional commit at a time with a complexity round-trip on each fix. |
| [`beta-release-readiness`](.apm/skills/beta-release-readiness/SKILL.md) | Single-pass go/no-go check for shipping to early users: walk a checklist (core-path correctness, error handling, config & secrets, observability, critical-path tests, beta docs, rollback, known-gaps disclosure) calibrated to the beta bar, and report a verdict with blocking/non-blocking gaps. |
| [`test-quality`](.apm/skills/test-quality/SKILL.md) | Measure Go test-suite strength (mutation testing via `gomutants` + per-test coverage-contribution analysis); emit a quantitative scorecard, a test contribution map, and ranked LLM-actionable findings, then work them one commit at a time. |

_(commands: [`architecture-review`](.apm/prompts/architecture-review.prompt.md), [`beta-release-readiness`](.apm/prompts/beta-release-readiness.prompt.md), [`test-quality`](.apm/prompts/test-quality.prompt.md))_

## Layout

```
.apm/                              APM package sources (the source of truth)
  skills/<name>/                     one directory per skill: SKILL.md + any helper scripts
  prompts/<name>.prompt.md           slash-command / APM prompt wrappers (one file
                                      compiles to a Copilot prompt AND a Claude slash
                                      command — installs to .claude/commands/)
  instructions/<name>.instructions.md  shared rules (compiled into AGENTS.md / .claude/rules/)
.claude/
  skills/<name>/                    committed mirror of .apm/skills/<name>/ — see `make sync`
apm.yml                            APM manifest (targets: claude, copilot; also declares
                                    `scripts:` — see Scripts below)
Makefile                           list / sync / check / lint
```

`.apm/skills/<name>/` is authoritative. `.claude/skills/<name>/` is a byte copy
so a bare checkout is usable without APM. `make check` fails on drift, `make
sync` rebuilds the mirror, `make lint` runs `ruff` + `py_compile` + `bash -n`
over every helper script.

## Use it

### As an APM dependency

From the consuming project:

```bash
apm install github.com/dioad/agent-skills --target claude
# -> deploys every skill to .claude/skills/<name>/ (helper scripts included)
```

Then ask the agent to run a skill by name (e.g. "run the test-quality skill"), or
invoke its command.

### As plain Claude skills (no APM)

Copy the skill directories you want into a place Claude loads skills from:

```bash
cp -r .claude/skills/test-quality  /path/to/your/repo/.claude/skills/   # project-scoped
cp -r .claude/skills/test-quality  ~/.claude/skills/                    # user-scoped
```

## Adding a skill

1. Create `.apm/skills/<name>/SKILL.md` (plus any helper scripts beside it).
2. Optionally add `.apm/prompts/<name>.prompt.md` and/or
   `.apm/instructions/<name>.instructions.md`.
3. Make helper scripts location-independent — resolve the target repo with
   `git rev-parse --show-toplevel`, not a hardcoded `.claude/...` path.
4. `make sync && make check && make lint`.
5. Add a row to the table above.

## Scripts

`apm.yml` declares one script, run on demand with `apm run <name>` — not
automatically on `apm install` (APM has no postinstall hook):

- **`gograph-setup`** — runs `gograph add-claude-plugin` in the consuming
  repo. Requires the `gograph` CLI on `PATH` (`brew install
  ozgurcd/homebrew-tap/gograph`). Installs gograph's own CLAUDE.md steering
  rules, MCP registration prompt, and PreToolUse hook, generated live by the
  tool's current version — so there is no hand-copied gograph reference in
  this package to go stale.

## Per-skill requirements

- **architecture-review** — `gocognit` on `PATH` (complexity baseline/round-trip
  in Phase 2); `gh` for filing out-of-scope findings upstream. Phase 1 needs no
  tooling.
- **beta-release-readiness** — no tooling required; language- and stack-agnostic.
- **test-quality** — `go`, `python3` (3.11+), and `gomutants` on `PATH`;
  `gocognit` optional (adds the risk section).
