SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= prod
IMAGE_TAG ?= latest
config ?= ../config.yaml

image := $(shell yq .notebook.image ${config})
platform := --platform $(shell yq .notebook.platform ${config})

ifeq ($(ENV),dev)
	TAG := dev
else
	TAG := $(IMAGE_TAG)
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Build Docker image
	docker build ${platform} -t ${image}:${TAG} .

.PHONY: push
push: build ## Build and push Docker image
	docker push ${image}:${TAG}

.PHONY: clean
clean: ## Remove Docker image
	docker rmi ${image}:${TAG} || true
