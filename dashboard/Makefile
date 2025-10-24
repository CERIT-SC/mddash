SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= prod
IMAGE_TAG ?= latest

config := ../config.yaml
image := $(shell yq .dashboard.image $(config))
platform := --platform $(shell yq .dashboard.platform $(config))

ifeq ($(ENV),dev)
	tag := dev
	dockerfile := Dockerfile.dev
	build_args := --build-arg IMAGE=$(image):latest
else
	tag := $(IMAGE_TAG)
	dockerfile := Dockerfile
	build_args :=
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Build Docker image (ENV=dev for dev, ENV=prod for prod)
	docker build $(platform) -f $(dockerfile) $(build_args) -t $(image):$(tag) .

.PHONY: push
push: build ## Build and push Docker image
	docker push $(image):$(tag)

.PHONY: clean
clean: ## Remove Docker images
	docker rmi $(image):$(tag) || true
