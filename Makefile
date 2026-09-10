# .apm/ holds the APM package sources: skills/<name>/, commands/<name>.md, and
# (later) instructions/<name>.instructions.md.
#
# .claude/skills/<name>/ is a committed mirror of .apm/skills/<name>/ so every
# skill works from a plain checkout without running `apm install`. `make sync`
# rebuilds the mirror; `make check` fails if it has drifted.

SKILLS := $(notdir $(wildcard .apm/skills/*))

.PHONY: sync check lint list

list: ## List the skills in this collection
	@for s in $(SKILLS); do echo "  $$s"; done

sync: ## Mirror .apm/skills/* -> .claude/skills/*
	@for s in $(SKILLS); do \
	  echo "sync $$s"; \
	  rm -rf .claude/skills/$$s; \
	  mkdir -p .claude/skills/$$s; \
	  cp -R .apm/skills/$$s/. .claude/skills/$$s/; \
	  find .claude/skills/$$s -name '*.sh' -exec chmod +x {} + ; \
	  find .claude/skills/$$s -name '*.py' -exec chmod +x {} + ; \
	done

check: ## Fail if any mirror has drifted from its source
	@for s in $(SKILLS); do \
	  echo "check $$s"; \
	  diff -rq -x __pycache__ -x '*.pyc' .apm/skills/$$s .claude/skills/$$s; \
	done

lint: ## Static-check helper scripts across all skills
	@find .apm/skills -name '*.py' -print -exec ruff check {} + -exec python3 -m py_compile {} +
	@find .apm/skills -name '*.sh' -print -exec bash -n {} +
