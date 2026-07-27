SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev

ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
endif

config := $(if $(wildcard ../config.${ENV}.yaml),../config.${ENV}.yaml,../config.yaml)
registry := $(shell yq -r '.registry' $(config))
image := $(registry)/$(shell yq -r '.tuner.api.image' $(config))
namespace := $(shell yq -r '.namespace' $(config))

.PHONY: help test build push clean e2e

help: ## Show help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

test: ## Run unit tests
	uv run pytest

build: ## Build the Tuner API image
	docker build --platform linux/amd64 -f Dockerfile -t $(image):$(IMAGE_TAG) ..

push: build ## Build and push the Tuner API image
	docker push $(image):$(IMAGE_TAG)

clean: ## Remove the local Tuner API image
	docker rmi $(image):$(IMAGE_TAG) || true

e2e: ## Run API E2E tests against a Kubernetes deployment
	@set -euo pipefail; \
	api_base_url="http://127.0.0.1:18000/api"; \
	user="$$(kubectl get secret "tuner-auth" -n "$(namespace)" -o jsonpath='{.data.user}' | base64 --decode)"; \
	password="$$(kubectl get secret "tuner-auth" -n "$(namespace)" -o jsonpath='{.data.password}' | base64 --decode)"; \
	log_file="$$(mktemp /tmp/tuner-port-forward.XXXXXX.log)"; \
	kubectl port-forward -n "$(namespace)" "svc/tuner-api-svc" "18000:8000" >"$$log_file" 2>&1 & \
	pf_pid="$$!"; \
	trap 'kill "'"$$pf_pid"'" 2>/dev/null || true; rm -f "'"$$log_file"'"' EXIT; \
	ready=0; \
	for _ in {1..30}; do \
		if python3 -c "import urllib.request; urllib.request.urlopen('$$api_base_url/health', timeout=2).read()" >/dev/null 2>&1; then \
			ready=1; \
			break; \
		fi; \
		if ! kill -0 "$$pf_pid" 2>/dev/null; then \
			printf 'kubectl port-forward exited before API became reachable. Log: %s\n' "$$log_file" >&2; \
			exit 1; \
		fi; \
		sleep 1; \
	done; \
	if [ "$$ready" != 1 ]; then \
		printf 'Timed out waiting for %s. Port-forward log: %s\n' "$$api_base_url/health" "$$log_file" >&2; \
		exit 1; \
	fi; \
	E2E_API_BASE_URL="$$api_base_url" \
	E2E_TUNER_USER="$$user" \
	E2E_TUNER_PASSWORD="$$password" \
	uv run pytest tests/e2e $(PYTEST_ARGS)
