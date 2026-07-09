SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev

# IMAGE_TAG inherited from parent Makefile (exported), or computed here
ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
else
  IMAGE_TAG ?= sha-$(shell git rev-parse --short HEAD)
endif

#config := $(if $(filter dev,$(ENV)),../config.dev.yaml,../config.yaml)
config := $(if $(wildcard ../config.${ENV}.yaml),../config.${ENV}.yaml,../config.yaml)

registry := $(shell yq .registry $(config))
image := $(registry)/$(shell yq .mdrunApi.image $(config))
platform := --platform $(shell yq .mdrunApi.platform $(config))

ifeq ($(ENV),dev)
	tag := dev
else
	tag := $(IMAGE_TAG)
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: ## Run tests
	uv run pytest

.PHONY: build
build: ## Build Docker image (ENV=dev for dev, ENV=prod for prod)
	docker build $(platform) -f Dockerfile -t $(image):$(tag) ..

.PHONY: push
push: build ## Build and push Docker image
	docker push $(image):$(tag)

.PHONY: clean
clean: ## Remove Docker image
	docker rmi $(image):$(tag) || true

.PHONY: clean-all
clean-all: ## Remove both dev and prod images
	docker rmi $(image):dev || true
	docker rmi $(image):$(IMAGE_TAG) || true
