SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev
IMAGE_TAG ?= latest

config := $(if $(filter dev,$(ENV)),../config.dev.yaml,../config.yaml)
platform := --platform $(shell yq '.sidecars.platform' $(config))

# Image names from config
ui_image := $(shell yq '.sidecars.ui.image' $(config))
proxy_image := $(shell yq '.sidecars.proxy.image' $(config))
auth_image := $(shell yq '.sidecars.auth.image' $(config))
api_image := $(shell yq '.sidecars.api.image' $(config))
s3sync_image := $(shell yq '.sidecars.s3sync.image' $(config))

ifeq ($(ENV),dev)
	tag := dev
	# Use dev Dockerfiles for Flask apps (debug mode, hot reload)
	api_dockerfile := Dockerfile.dev
	auth_dockerfile := Dockerfile.dev
else
	tag := $(IMAGE_TAG)
	api_dockerfile := Dockerfile
	auth_dockerfile := Dockerfile
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "ENV=$(ENV), TAG=$(tag)"

# Build targets
.PHONY: build
build: build-ui build-proxy build-auth build-api build-s3sync ## Build all sidecar images

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
	docker build $(platform) -f auth/$(auth_dockerfile) -t $(auth_image):$(tag) auth/

.PHONY: build-api
build-api: ## Build API image
	docker build $(platform) -f api/$(api_dockerfile) -t $(api_image):$(tag) api/

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
	cd ui && npm run dev

.PHONY: dev-api
dev-api: ## Run API dev server (hot reload)
	cd api && python app.py
