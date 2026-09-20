---
name: makefile
description: ALWAYS use this skill when creating, modifying, or debugging Makefiles, make targets, or command-driven build automation.
---

# Makefile Standards

## Syntax

- Recipe lines must start with a tab.
- Declare non-file targets with `.PHONY`.
- Use `:=` for values evaluated once.
- Use `?=` for user-overridable defaults.
- Escape shell variables as `$$var` inside recipes.

## Command Surface

- Top-level developer Makefiles should expose `help`, `setup`, `test`, `lint`, `build`, and `clean` when relevant.
- Use standard target names for common actions: `setup`, `install`, `dev`, `test`, `lint`, `format`, `typecheck`, `build`, `clean`, `deploy`, and `help`.
- Use this help-target convention for top-level developer Makefiles:

```makefile
.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
```

- Put dangerous or environment-specific targets behind explicit variables or confirmation checks.
- Handle expected missing files explicitly instead of masking target failures.

## Shell Behavior

- Set `SHELL` only when recipes require a specific shell.
- Quote variables passed into shell commands.
- Validate required variables before deploy, publish, migration, or destructive targets.
- Prefer small scripts when a recipe becomes complex enough to need substantial shell logic.

## Verification

- Run the affected target after changing a Makefile.
- For reusable Makefiles, verify includes and variable overrides from at least one consumer.
