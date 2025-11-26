SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= prod
IMAGE_TAG ?= latest

config := $(if $(filter dev,$(ENV)),../config.dev.yaml,../config.yaml)
platform := --platform linux/amd64

# Container images
proxy_image := $(shell yq '.dashboard.containers.proxy.image' $(config))
api_image := $(shell yq '.dashboard.containers.api.image' $(config))
jupyter_image := $(shell yq '.dashboard.containers.jupyter.image' $(config))
s3sync_image := $(shell yq '.dashboard.containers.s3Sync.image' $(config))

ifeq ($(ENV),dev)
	tag := dev
else
	tag := $(IMAGE_TAG)
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Images:"
	@echo "  proxy:   $(proxy_image):$(tag)"
	@echo "  api:     $(api_image):$(tag)"
	@echo "  jupyter: $(jupyter_image):$(tag)"
	@echo "  s3-sync: $(s3sync_image):$(tag)"

.PHONY: build-proxy
build-proxy: ## Build proxy container image
	docker build $(platform) -f containers/proxy/Dockerfile -t $(proxy_image):$(tag) .

.PHONY: build-api
build-api: ## Build API container image
	docker build $(platform) -f containers/api/Dockerfile -t $(api_image):$(tag) .

.PHONY: build-jupyter
build-jupyter: ## Build Jupyter container image
	docker build $(platform) -f containers/jupyter/Dockerfile -t $(jupyter_image):$(tag) .

.PHONY: build-s3-sync
build-s3-sync: ## Build S3 sync container image
	docker build $(platform) -f containers/s3-sync/Dockerfile -t $(s3sync_image):$(tag) .

.PHONY: build
build: build-proxy build-api build-jupyter build-s3-sync ## Build all container images

.PHONY: push-proxy
push-proxy: build-proxy ## Build and push proxy image
	docker push $(proxy_image):$(tag)

.PHONY: push-api
push-api: build-api ## Build and push API image
	docker push $(api_image):$(tag)

.PHONY: push-jupyter
push-jupyter: build-jupyter ## Build and push Jupyter image
	docker push $(jupyter_image):$(tag)

.PHONY: push-s3-sync
push-s3-sync: build-s3-sync ## Build and push S3 sync image
	docker push $(s3sync_image):$(tag)

.PHONY: push
push: push-proxy push-api push-jupyter push-s3-sync ## Build and push all images

.PHONY: clean
clean: ## Remove Docker images
	docker rmi $(proxy_image):$(tag) || true
	docker rmi $(api_image):$(tag) || true
	docker rmi $(jupyter_image):$(tag) || true
	docker rmi $(s3sync_image):$(tag) || true
