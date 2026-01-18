---
applyTo: '**/Makefile, **/*.mk'
---

# Makefile Guidelines

Rules for writing robust, portable Makefiles.

<context>
Essential Makefile patterns for build automation. Focus on correct syntax, proper variable usage, and common patterns.
</context>

<best_practices>

<syntax>
### Mandatory Syntax
**Recipes MUST use TAB (not spaces):**
```makefile
target: prereq
	command    # TAB before this line
```

### Variable Assignment
```makefile
VAR := value    # Simple (evaluate once) - PREFER
VAR = value     # Recursive (evaluate each use)
VAR ?= value    # Set only if undefined
VAR += value    # Append
```

### Automatic Variables
| Var | Meaning |
|-----|---------|
| `$@` | Target name |
| `$<` | First prerequisite |
| `$^` | All prerequisites |
| `$?` | Newer prerequisites |

```makefile
%.o: %.c
	$(CC) -c $< -o $@
```
</syntax>

<patterns>
### .PHONY Targets
Always declare non-file targets:
```makefile
.PHONY: all build clean test help
```

### Help Target (Required)
```makefile
.PHONY: help
help: ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
```

### Error Handling
```makefile
clean:
	rm -rf build/ || true    # Continue on error

deploy:
	@[ -n "$(ENV)" ] || { echo "Error: ENV not set" >&2; exit 1; }
	./deploy.sh $(ENV)
```

### Multi-line Commands
```makefile
deploy:
	docker run \
		-e ENV=prod \
		-v $(PWD):/app \
		image
```
</patterns>

<security>
### Security
```makefile
# NEVER hardcode secrets
ifndef API_KEY
$(error API_KEY not set)
endif

# Set SHELL for consistency
SHELL := /bin/bash

# Quote variables in shell
backup:
	tar czf "backup-$$(date +%Y%m%d).tar.gz" "$(DIR)"
```
</security>

<template>
### Template
```makefile
SHELL := /bin/bash
.DEFAULT_GOAL := help

CONFIG ?= config.yaml
IMAGE := $(shell yq .image $(CONFIG))

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Build project
	docker build -t $(IMAGE) .

.PHONY: test
test: ## Run tests
	pytest tests/

.PHONY: clean
clean: ## Clean artifacts
	rm -rf build/ || true
```
</template>

<anti_patterns>
### Common Pitfalls
| Wrong | Right |
|-------|-------|
| Spaces for indent | TAB character |
| `VAR = $(shell ...)` | `VAR := $(shell ...)` |
| Missing `.PHONY` | `.PHONY: clean test` |
| `rm file` (fails) | `rm file \|\| true` |
| Shell var `$files` | `$$files` in recipes |
</anti_patterns>

</best_practices>

<boundaries>
- ✅ **Always:** Use TAB for recipe indentation
- ✅ **Always:** Declare `.PHONY` for non-file targets
- ✅ **Always:** Include a `help` target
- ✅ **Always:** Use `:=` for shell commands
- ✅ **Always:** Quote variables in shell commands
- 🚫 **Never:** Hardcode secrets
- 🚫 **Never:** Use spaces instead of TABs
- 🚫 **Never:** Forget `$$` for shell variables in recipes
</boundaries>
