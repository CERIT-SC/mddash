SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= prod
IMAGE_TAG ?= latest
config ?= ../config.yaml

image := $(shell yq .dashboard.image ${config})
platform := --platform $(shell yq .dashboard.platform ${config})

ifeq ($(ENV),dev)
	TAG := dev
	DOCKERFILE := Dockerfile.dev
	BUILD_ARGS := --build-arg IMAGE=${image}:latest
else
	TAG := $(IMAGE_TAG)
	DOCKERFILE := Dockerfile
	BUILD_ARGS :=
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Build Docker image (ENV=dev for dev, ENV=prod for prod)
	docker build ${platform} -f ${DOCKERFILE} ${BUILD_ARGS} -t ${image}:${TAG} .

.PHONY: push
push: build ## Build and push Docker image
	docker push ${image}:${TAG}

.PHONY: clean
clean: ## Remove Docker images
	docker rmi ${image}:${TAG} || true
