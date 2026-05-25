SHELL := /bin/bash
.DEFAULT_GOAL := help

CURRENT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
ENV ?= $(if $(filter master,$(CURRENT_BRANCH)),prod,dev)

# Tagging: dev uses static 'dev' tag, prod uses '<short-sha>' for unique, traceable images
ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
else
  IMAGE_TAG ?= $(shell git rev-parse --short HEAD)
endif
export IMAGE_TAG

#config := $(if $(filter dev,$(ENV)),config.dev.yaml,config.yaml)
config := $(if $(wildcard config.${ENV}.yaml),config.${ENV}.yaml,config.yaml)

namespace := $(shell yq '.namespace' $(config))
registry := $(shell yq '.registry' $(config))

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Current: BRANCH=$(CURRENT_BRANCH), ENV=$(ENV), TAG=$(IMAGE_TAG), NS=$(namespace)"

# ==================== FORMAT / LINT ====================

.PHONY: format
format: ## Format and lint-fix all code (Python via ruff, frontend via prettier)
	ruff format .
	ruff check . --fix
	cd dashboard/ui && pnpm run format

.PHONY: lint
lint: ## Check Python linting without auto-fix
	ruff check .

# ==================== TYPE CHECK ====================

.PHONY: type-check
type-check: type-check-dashboard-api type-check-dashboard-auth type-check-mdrun-api type-check-ui ## Run type checks on all components

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

# ==================== TEST ====================

.PHONY: test
test: test-dashboard-api test-dashboard-auth test-mdrun-api ## Run all tests

.PHONY: test-dashboard-api
test-dashboard-api: ## Run dashboard API tests
	cd dashboard/api && uv run pytest

.PHONY: test-dashboard-auth
test-dashboard-auth: ## Run dashboard auth tests
	cd dashboard/auth && uv run pytest

.PHONY: test-mdrun-api
test-mdrun-api: ## Run mdrun-api tests
	cd mdrun-api && uv run pytest

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

.PHONY: push-mdrun-api-chart
push-mdrun-api-chart: ## Package and push mdrun-api Helm chart to OCI registry
	$(eval CHART_VERSION := $(shell yq '.version' helm/charts/mdrun-api/Chart.yaml))
	helm package helm/charts/mdrun-api --version $(CHART_VERSION) --app-version $(IMAGE_TAG)
	helm push mdrun-api-$(CHART_VERSION).tgz oci://$(registry)
	rm -f mdrun-api-$(CHART_VERSION).tgz

.PHONY: deploy
deploy: ## Deploy via Helm
	@$(MAKE) -C helm deploy ENV=$(ENV)

.PHONY: all
all: build push deploy ## Build, push, and deploy everything

.PHONY: clean
clean: ## Uninstall Helm release
	@$(MAKE) -C helm uninstall ENV=$(ENV)

.PHONY: status
status: ## Show deployment status
	@$(MAKE) -C helm status ENV=$(ENV)

.PHONY: logs
logs: ## Show deployment logs
	@$(MAKE) -C helm logs ENV=$(ENV)

mdrun_api_values := $(if $(filter dev,$(ENV)),helm/charts/mdrun-api/values.dev.yaml,helm/charts/mdrun-api/values.yaml)

.PHONY: resources
resources: ## Show resource budget and recommended namespace quota values (offline)
	@python3 scripts/resource_summary.py $(config) $(mdrun_api_values)

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
