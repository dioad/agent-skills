# agent-skills

Shared agent skills, commands, and instructions for dioad Go projects,
distributed as an [APM](https://microsoft.github.io/apm) package. Each skill also
works standalone — copy its directory into any `.claude/skills/`.

## Contents

| Skill | What it does |
|---|---|
| [`test-quality`](.apm/skills/test-quality/SKILL.md) | Measure Go test-suite strength (mutation testing via `gomutants` + per-test coverage-contribution analysis); emit a quantitative scorecard, a test contribution map, and ranked LLM-actionable findings, then work them one commit at a time. |

_(commands: [`test-quality`](.apm/commands/test-quality.md))_

## Layout

```
.apm/                              APM package sources (the source of truth)
  skills/<name>/                     one directory per skill: SKILL.md + any helper scripts
  commands/<name>.md                 slash-command / APM command wrappers
  instructions/<name>.instructions.md  shared rules (compiled into AGENTS.md / .claude/rules/)
.claude/
  skills/<name>/                    committed mirror of .apm/skills/<name>/ — see `make sync`
apm.yml                            APM manifest (targets: claude, copilot)
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
2. Optionally add `.apm/commands/<name>.md` and/or
   `.apm/instructions/<name>.instructions.md`.
3. Make helper scripts location-independent — resolve the target repo with
   `git rev-parse --show-toplevel`, not a hardcoded `.claude/...` path.
4. `make sync && make check && make lint`.
5. Add a row to the table above.

## Per-skill requirements

- **test-quality** — `go`, `python3` (3.11+), and `gomutants` on `PATH`;
  `gocognit` optional (adds the risk section).
