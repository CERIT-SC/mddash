SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev
IMAGE_TAG ?= latest

config := $(if $(filter dev,$(ENV)),../config.dev.yaml,../config.yaml)
image := $(shell yq .notebook.image $(config))
platform := --platform $(shell yq .notebook.platform $(config))

ifeq ($(ENV),dev)
	tag := dev
else
	tag := $(IMAGE_TAG)
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Build Docker image
	docker build $(platform) -t $(image):$(tag) .

.PHONY: push
push: build ## Build and push Docker image
	docker push $(image):$(tag)

.PHONY: clean
clean: ## Remove Docker image
	docker rmi $(image):$(tag) || true
