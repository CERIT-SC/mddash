SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev

# IMAGE_TAG inherited from parent Makefile (exported), or computed here
ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
endif

config := $(if $(wildcard ../config.${ENV}.yaml),../config.${ENV}.yaml,../config.yaml)

platform := --platform $(shell yq '.sidecars.platform' $(config))

# Image names from config
registry := $(shell yq '.registry' $(config))
ui_image := $(registry)/$(shell yq '.sidecars.ui.image' $(config))
proxy_image := $(registry)/$(shell yq '.sidecars.proxy.image' $(config))
auth_image := $(registry)/$(shell yq '.sidecars.auth.image' $(config))
api_image := $(registry)/$(shell yq '.sidecars.api.image' $(config))
s3sync_image := $(registry)/$(shell yq '.sidecars.s3sync.image' $(config))

tag := $(IMAGE_TAG)

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "ENV=$(ENV), TAG=$(tag)"

# ==================== TEST ====================

.PHONY: test
test: test-api test-auth ## Run all dashboard tests

.PHONY: test-api
test-api: ## Run API tests
	cd api && uv run pytest

.PHONY: test-auth
test-auth: ## Run auth tests
	cd auth && uv run pytest

# ==================== BUILD ====================

# Build targets
.PHONY: build
build: build-proxy build-auth build-api build-s3sync ## Build all sidecar images

.PHONY: build-ui
build-ui: ## Build UI image (React static files)
	docker build $(platform) -f ui/Dockerfile -t $(ui_image):$(tag) ui/

.PHONY: build-proxy
build-proxy: build-ui ## Build proxy image (Caddy + UI static files)
	docker build $(platform) -f proxy/Dockerfile \
		--build-arg UI_IMAGE=$(ui_image):$(tag) \
		-t $(proxy_image):$(tag) proxy/

.PHONY: build-auth
build-auth: ## Build auth image
	docker build $(platform) -f auth/Dockerfile -t $(auth_image):$(tag) ..

.PHONY: build-api
build-api: ## Build API image
	docker build $(platform) -f api/Dockerfile -t $(api_image):$(tag) ..

.PHONY: build-s3sync
build-s3sync: ## Build s3-sync image
	docker build $(platform) -f s3-sync/Dockerfile -t $(s3sync_image):$(tag) s3-sync/

# Push targets
.PHONY: push
push: push-ui push-proxy push-auth push-api push-s3sync ## Build and push all sidecar images

.PHONY: push-ui
push-ui: build-ui ## Build and push UI image
	docker push $(ui_image):$(tag)

.PHONY: push-proxy
push-proxy: build-proxy ## Build and push proxy image
	docker push $(proxy_image):$(tag)

.PHONY: push-auth
push-auth: build-auth ## Build and push auth image
	docker push $(auth_image):$(tag)

.PHONY: push-api
push-api: build-api ## Build and push API image
	docker push $(api_image):$(tag)

.PHONY: push-s3sync
push-s3sync: build-s3sync ## Build and push s3-sync image
	docker push $(s3sync_image):$(tag)

# Clean targets
.PHONY: clean
clean: ## Remove all Docker images
	docker rmi $(ui_image):$(tag) 2>/dev/null || true
	docker rmi $(proxy_image):$(tag) 2>/dev/null || true
	docker rmi $(auth_image):$(tag) 2>/dev/null || true
	docker rmi $(api_image):$(tag) 2>/dev/null || true
	docker rmi $(s3sync_image):$(tag) 2>/dev/null || true

# Development helpers
.PHONY: dev-ui
dev-ui: ## Run UI dev server (hot reload)
	cd ui && pnpm run dev

.PHONY: dev-api
dev-api: ## Run API dev server (hot reload)
	cd api && uv run python app.py
