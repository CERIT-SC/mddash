SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= prod
IMAGE_TAG ?= $(if $(filter dev,$(ENV)),dev,latest)

config := config.yaml
namespace := $(shell yq '.$(ENV)Namespace' $(config))
chart_registry := $(shell yq '.mdrunApiChart.registry' $(config))
chart_repo := $(shell yq '.mdrunApiChart.repository' $(config))

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Current: ENV=$(ENV), TAG=$(IMAGE_TAG), NS=$(namespace)"

.PHONY: build
build: build-dashboard build-notebook build-mdrun-api ## Build all images

.PHONY: build-dashboard
build-dashboard: ## Build dashboard image
	@$(MAKE) -C dashboard build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: build-notebook
build-notebook: ## Build notebook image
	@$(MAKE) -C notebook build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: build-mdrun-api
build-mdrun-api: ## Build mdrun-api image
	@$(MAKE) -C mdrun-api build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: push
push: push-dashboard push-notebook push-mdrun-api ## Build and push all images

.PHONY: push-dashboard
push-dashboard: ## Build and push dashboard image
	@$(MAKE) -C dashboard push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: push-notebook
push-notebook: ## Build and push notebook image
	@$(MAKE) -C notebook push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: push-mdrun-api
push-mdrun-api: ## Build and push mdrun-api image
	@$(MAKE) -C mdrun-api push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

.PHONY: push-mdrun-api-chart
push-mdrun-api-chart: ## Package and push mdrun-api Helm chart to OCI registry
	$(eval CHART_VERSION := $(shell yq '.version' helm/charts/mdrun-api/Chart.yaml))
	helm package helm/charts/mdrun-api --version $(CHART_VERSION) --app-version $(IMAGE_TAG)
	helm push mdrun-api-$(CHART_VERSION).tgz oci://$(chart_registry)/$(chart_repo)
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

.PHONY: demo
demo: ## Run local demo (Flask API + React dev server)
	@echo "Starting Flask API..."; \
	python3 dashboard/api/_demo.py & \
	API_PID=$$!; \
	echo "Flask API started (PID: $$API_PID)"; \
	echo "Starting React dev server..."; \
	cd dashboard/dash && npm run dev & \
	VITE_PID=$$!; \
	echo "React dev server started (PID: $$VITE_PID)"; \
	echo "Demo running - Press Ctrl+C to stop"; \
	trap "echo 'Stopping...'; kill $$API_PID $$VITE_PID 2>/dev/null; exit" INT TERM EXIT; \
	wait || true
