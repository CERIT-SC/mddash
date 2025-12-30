---
applyTo: '**/Makefile, **/*.mk'
---

# Makefile Rules for AI Agents

## Mandatory Syntax
**Recipes MUST use TAB (not spaces)**
```makefile
target: prereq
	command    # TAB before this line
```

## Variable Assignment
```makefile
VAR := value    # Simple (evaluate once) - PREFER THIS
VAR = value     # Recursive (evaluate each use)
VAR ?= value    # Set only if undefined
VAR += value    # Append
```

## Automatic Variables
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

## .PHONY Targets
ALWAYS declare non-file targets:
```makefile
.PHONY: all build clean test help
```

## Core Patterns

### Help Target (Required)
```makefile
.PHONY: help
help: ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
```

### Pattern Rules
```makefile
%.o: %.c %.h
	$(CC) $(CFLAGS) -c $< -o $@

%.yaml: %.yaml.j2 config.yaml
	jinja2 $< config.yaml -o $@
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

install:
	@for f in $(YAMLS); do kubectl apply -f $$f; done
```

## Security Rules
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

## Common Pitfalls
| Wrong | Right |
|-------|-------|
| Spaces for indent | TAB character |
| `VAR = $(shell ...)` | `VAR := $(shell ...)` |
| Missing `.PHONY` | `.PHONY: clean test` |
| `rm file` (fails) | `rm file \|\| true` |
| Shell var `$$files` | `$${files}` in loops |

## Standard Template
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

## Quick Reference
**Variable Assignment:** `:=` (once), `=` (each use), `?=` (if unset), `+=` (append)  
**Auto Variables:** `$@` (target), `$<` (first prereq), `$^` (all prereqs)  
**Special Targets:** `.PHONY`, `.SECONDARY`, `.PRECIOUS`, `.DEFAULT_GOAL`  
**Silent:** `@command` suppresses echo  
**Escape:** Use `$$` for shell variables in recipes
