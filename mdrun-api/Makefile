SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev
IMAGE_TAG ?= latest

config := $(if $(filter dev,$(ENV)),../config.dev.yaml,../config.yaml)
image := $(shell yq .mdrunApi.image $(config))
platform := --platform $(shell yq .mdrunApi.platform $(config))

ifeq ($(ENV),dev)
	tag := dev
	dockerfile := Dockerfile.dev
else
	tag := $(IMAGE_TAG)
	dockerfile := Dockerfile
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: ## Run tests
	pip install -q -r requirements-dev.txt && pytest

.PHONY: build
build: ## Build Docker image (ENV=dev for dev, ENV=prod for prod)
	docker build $(platform) -f $(dockerfile) -t $(image):$(tag) .

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
