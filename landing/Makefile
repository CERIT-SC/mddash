SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev

ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
endif

config := $(if $(wildcard ../config.${ENV}.yaml),../config.${ENV}.yaml,../config.yaml)

registry := $(shell yq '.registry' $(config))
image := $(registry)/$(shell yq '.landing.image' $(config))
platform := --platform $(shell yq '.sidecars.platform' $(config))

tag := $(IMAGE_TAG)

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: format
format: ## Format source files with Prettier
	pnpm run format

.PHONY: build
build: ## Build Docker image
	docker build $(platform) -t $(image):$(tag) .

.PHONY: push
push: build ## Build and push Docker image
	docker push $(image):$(tag)

.PHONY: clean
clean: ## Remove Docker image
	docker rmi $(image):$(tag) || true
