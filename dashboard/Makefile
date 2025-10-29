SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= prod
IMAGE_TAG ?= latest

config := ../config.yaml
image := $(shell yq .dashboard.image $(config))
platform := --platform $(shell yq .dashboard.platform $(config))

ifeq ($(ENV),dev)
	tag := dev
	build_target := build-dev
else
	tag := $(IMAGE_TAG)
	build_target := build-prod
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: build-prod
build-prod: ## Build production image
	docker build $(platform) -f Dockerfile -t $(image):$(IMAGE_TAG) .

.PHONY: build-dev
build-dev: build-prod ## Build dev image (depends on prod)
	docker build $(platform) -f Dockerfile.dev --build-arg IMAGE=$(image):$(IMAGE_TAG) -t $(image):dev .

.PHONY: build
build: $(build_target) ## Build image based on ENV (dev or prod)

.PHONY: push
push: build ## Build and push Docker image
	docker push $(image):$(tag)

.PHONY: clean
clean: ## Remove Docker images
	docker rmi $(image):$(tag) || true
