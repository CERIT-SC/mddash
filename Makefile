SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev

ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
else
  ifeq ($(IMAGE_TAG),)
    $(error IMAGE_TAG is required for ENV=$(ENV) (e.g. IMAGE_TAG=0.1.0))
  endif
endif
export IMAGE_TAG

config := $(if $(wildcard config.${ENV}.yaml),config.${ENV}.yaml,config.yaml)

namespace := $(shell yq -r '.namespace' $(config))
registry := $(shell yq -r '.registry' $(config))
chart_registry := $(registry)/charts

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Current: ENV=$(ENV), TAG=$(IMAGE_TAG), NS=$(namespace)"

# ==================== FORMAT / LINT ====================

.PHONY: fix
fix: ## Auto-fix formatting and lint issues (Python via ruff, frontend via prettier/eslint)
	ruff format .
	ruff check . --fix
	cd dashboard/ui && pnpm run format && pnpm exec eslint . --fix
	cd landing && pnpm run format

.PHONY: lint
lint: lint-py lint-ui ## Check linting without auto-fix

.PHONY: lint-py
lint-py: ## Check Python linting
	ruff check .

.PHONY: lint-ui
lint-ui: ## Check frontend linting (dashboard/ui via eslint)
	cd dashboard/ui && pnpm exec eslint . --max-warnings=0

.PHONY: lint-workflows
lint-workflows: ## Validate GitHub Actions workflows (actionlint + zizmor). Requires actionlint + zizmor (in devcontainer).
	actionlint
	zizmor --min-severity high .

.PHONY: format-check
format-check: format-check-py format-check-ui ## Check formatting without modifying files

.PHONY: format-check-py
format-check-py: ## Check Python formatting
	ruff format . --diff

.PHONY: format-check-ui
format-check-ui: ## Check frontend formatting (dashboard/ui and landing via prettier)
	cd dashboard/ui && pnpm run format:check
	cd landing && pnpm run format:check

.PHONY: lint-helm
lint-helm: validate-charts ## Validate all Helm charts including umbrella dependency build. Requires helm + gomplate + yq.
	helm repo add jupyterhub https://hub.jupyter.org/helm-chart/ >/dev/null
	helm repo update jupyterhub >/dev/null
	helm dependency build helm/charts/mddash
	helm lint helm/charts/mddash
	helm template mddash helm/charts/mddash >/dev/null

.PHONY: validate-charts
validate-charts: ## Lint mdrun-api chart and render values template. Requires helm + gomplate + yq.
	helm lint helm/charts/mdrun-api
	helm template mdrun-api helm/charts/mdrun-api >/dev/null
	$(MAKE) -C helm render

# ==================== TYPE CHECK ====================

.PHONY: type-check
type-check: type-check-dashboard-api type-check-dashboard-auth type-check-mdrun-api type-check-ui type-check-landing ## Run type checks on all components

.PHONY: type-check-dashboard-api
type-check-dashboard-api: ## Type-check dashboard API
	cd dashboard/api && uv run ty check .

.PHONY: type-check-dashboard-auth
type-check-dashboard-auth: ## Type-check dashboard auth
	cd dashboard/auth && uv run ty check .

.PHONY: type-check-mdrun-api
type-check-mdrun-api: ## Type-check mdrun-api
	cd mdrun-api && uv run ty check .

.PHONY: type-check-ui
type-check-ui: ## Type-check dashboard UI (TypeScript)
	cd dashboard/ui && pnpm run type-check

.PHONY: type-check-landing
type-check-landing: ## Type-check landing page (TypeScript)
	cd landing && pnpm run type-check

# ==================== TEST ====================

.PHONY: test
test: test-dashboard-api test-dashboard-auth test-mdrun-api test-pre-spawn-hook ## Run all tests

.PHONY: test-dashboard-api
test-dashboard-api: ## Run dashboard API tests
	cd dashboard/api && uv run pytest

.PHONY: test-dashboard-auth
test-dashboard-auth: ## Run dashboard auth tests
	cd dashboard/auth && uv run pytest

.PHONY: test-mdrun-api
test-mdrun-api: ## Run mdrun-api tests
	cd mdrun-api && uv run pytest

.PHONY: test-pre-spawn-hook
test-pre-spawn-hook: ## Run pre-spawn hook unit tests
	uv run --group dev pytest helm/charts/mddash/tests/

# ==================== BUILD ====================

.PHONY: build
build: build-dashboard build-notebook build-mdrun-api build-landing ## Build all images

.PHONY: build-dashboard
build-dashboard: ## Build dashboard sidecar images (ui, proxy, auth, api, s3sync)
	@$(MAKE) -C dashboard build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: build-notebook
build-notebook: ## Build notebook image
	@$(MAKE) -C notebook build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: build-mdrun-api
build-mdrun-api: ## Build mdrun-api image
	@$(MAKE) -C mdrun-api build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: build-landing
build-landing: ## Build landing page image
	@$(MAKE) -C landing build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: push
push: push-dashboard push-notebook push-mdrun-api push-landing ## Build and push all images

.PHONY: push-dashboard
push-dashboard: ## Build and push dashboard sidecar images
	@$(MAKE) -C dashboard push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: push-notebook
push-notebook: ## Build and push notebook image
	@$(MAKE) -C notebook push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: push-mdrun-api
push-mdrun-api: ## Build and push mdrun-api image
	@$(MAKE) -C mdrun-api push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: push-landing
push-landing: ## Build and push landing page image
	@$(MAKE) -C landing push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

# ==================== HELM CHART PACKAGING ====================

.PHONY: push-mdrun-api-chart
push-mdrun-api-chart: ## Package and push mdrun-api Helm chart to OCI registry
	$(eval CHART_VERSION := $(if $(VERSION),$(VERSION),$(IMAGE_TAG)))
	@[[ "$(CHART_VERSION)" =~ ^[0-9]+\.[0-9]+\.[0-9]+$$ ]] || { echo "VERSION or IMAGE_TAG must be strict SemVer x.y.z (got '$(CHART_VERSION)')" >&2; exit 1; }
	helm package helm/charts/mdrun-api --version $(CHART_VERSION) --app-version $(CHART_VERSION) --dependency-update
	helm push mdrun-api-$(CHART_VERSION).tgz oci://$(chart_registry)
	rm -f mdrun-api-$(CHART_VERSION).tgz

.PHONY: push-mddash-chart
push-mddash-chart: push-mdrun-api-chart ## Package and push umbrella Helm chart to OCI registry
	$(eval CHART_VERSION := $(if $(VERSION),$(VERSION),$(IMAGE_TAG)))
	@[[ "$(CHART_VERSION)" =~ ^[0-9]+\.[0-9]+\.[0-9]+$$ ]] || { echo "VERSION or IMAGE_TAG must be strict SemVer x.y.z (got '$(CHART_VERSION)')" >&2; exit 1; }
	@set -euo pipefail; \
		tmpdir="$$(mktemp -d)"; \
		trap 'rm -rf "$$tmpdir"' EXIT; \
		cp -a helm/charts/mddash/. "$$tmpdir"; \
		yq -i '(.dependencies[] | select(.name == "mdrun-api").version) = "$(CHART_VERSION)" | (.dependencies[] | select(.name == "mdrun-api").repository) = "oci://$(chart_registry)"' "$$tmpdir/Chart.yaml"; \
		helm dependency update "$$tmpdir"; \
		helm package "$$tmpdir" --destination "$$tmpdir" --version $(CHART_VERSION) --app-version $(CHART_VERSION); \
		helm push "$$tmpdir/mddash-jupyterhub-$(CHART_VERSION).tgz" oci://$(chart_registry)

.PHONY: deploy
deploy: ## Deploy via Helm
	@$(MAKE) -C helm deploy ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: release
release: ## Create and push an annotated release tag (usage: make release VERSION=x.y.z)
	@set -euo pipefail; \
		version="$(VERSION)"; \
		[[ "$$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$$ ]] || { echo "VERSION must be strict SemVer x.y.z (got '$$version')" >&2; exit 1; }; \
		[[ -z "$$(git status --porcelain)" ]] || { echo "Working tree must be clean before releasing" >&2; exit 1; }; \
		branch="$$(git symbolic-ref --quiet --short HEAD)" || { echo "Release must run from the master branch" >&2; exit 1; }; \
		[[ "$$branch" == master ]] || { echo "Release must run from the master branch (current: $$branch)" >&2; exit 1; }; \
		git fetch --quiet origin master; \
		[[ "$$(git rev-parse HEAD)" == "$$(git rev-parse origin/master)" ]] || { echo "Local master must match origin/master" >&2; exit 1; }; \
		tag="v$$version"; \
		if git rev-parse --verify --quiet "refs/tags/$$tag" >/dev/null || git ls-remote --exit-code --tags origin "refs/tags/$$tag" >/dev/null 2>&1; then \
			echo "Tag $$tag already exists" >&2; \
			exit 1; \
		fi; \
		git tag --annotate "$$tag" --message "Release $$tag"; \
		git push origin "$$tag"; \
		echo "Pushed $$tag; release.yml will run CI, deploy production, and create the GitHub Release."

.PHONY: all
ifeq ($(ENV),prod)
all:
	@echo "Production application releases must use a SemVer tag (e.g. v0.1.0)." >&2
	@echo "For operations: make {status|logs|history|rollback} ENV=prod" >&2
	@exit 1
else
all: build push deploy ## Build, push, and deploy everything (dev only)
endif

.PHONY: clean
clean: ## Uninstall Helm release
	@$(MAKE) -C helm uninstall ENV=$(ENV)

.PHONY: status
status: ## Show deployment status
	@$(MAKE) -C helm status ENV=$(ENV)

.PHONY: logs
logs: ## Show deployment logs
	@$(MAKE) -C helm logs ENV=$(ENV)

.PHONY: resources
resources: ## Show resource budget and recommended namespace quota values (offline)
	@python3 scripts/resource_summary.py $(config)

# ==================== ROLLBACK ====================

.PHONY: history
history: ## Show Helm release history
	@$(MAKE) -C helm history ENV=$(ENV)

.PHONY: rollback
rollback: ## Rollback to previous revision (REVISION=N for specific)
	@$(MAKE) -C helm rollback ENV=$(ENV) REVISION=$(REVISION)

.PHONY: demo
demo: ## Run local demo (real Flask API in demo profile + React dev server)
	@echo "Starting Flask API..."; \
	PORT=8888 uv run --directory dashboard/api python _demo/app.py & \
	API_PID=$$!; \
	echo "Flask API started (PID: $$API_PID)"; \
	echo "Starting React dev server..."; \
	cd dashboard/ui && pnpm run dev & \
	VITE_PID=$$!; \
	echo "React dev server started (PID: $$VITE_PID)"; \
	echo "Demo running - Press Ctrl+C to stop"; \
	trap "echo 'Stopping...'; kill $$API_PID $$VITE_PID 2>/dev/null; exit" INT TERM EXIT; \
	wait || true
