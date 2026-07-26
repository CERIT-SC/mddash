SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev

config := $(if $(wildcard ../../config.${ENV}.yaml),../../config.${ENV}.yaml,../../config.yaml)

REGISTRY         ?= $(shell yq -r '.registry' $(config))
AMBER_IMAGE_NAME ?= amber
AMBER_VERSION    ?= 26
AMBER_IMAGE      := $(REGISTRY)/$(AMBER_IMAGE_NAME):$(AMBER_VERSION)

IMAGE_NAME ?= tuner-worker
TAG        ?= gmx-2026.1_amber-26_ray-2.54.0_py-3.13
IMAGE      := $(REGISTRY)/$(IMAGE_NAME):$(TAG)

.PHONY: help build-amber push-amber build push clean tag

help: ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

PMEMD_TARBALL ?= pmemd26.tar.bz2

build-amber: ## Build AMBER base image (place pmemd tarball in worker/, set PMEMD_TARBALL=filename)
	docker build -t $(AMBER_IMAGE) -f Dockerfile.amber \
		--build-arg PMEMD_TARBALL=$(PMEMD_TARBALL) \
		.

push-amber: build-amber ## Build and push AMBER base image to private registry
	@[ -n "$(REGISTRY)" ] || { echo "Error: REGISTRY not set" >&2; exit 1; }
	docker push $(AMBER_IMAGE)

build: ## Build worker image (requires $(AMBER_IMAGE) in registry — run push-amber first)
	docker build --build-arg AMBER_IMAGE=$(AMBER_IMAGE) -t $(IMAGE) -f Dockerfile .

push: build ## Build and push worker image
	@[ -n "$(REGISTRY)" ] || { echo "Error: REGISTRY not set" >&2; exit 1; }
	docker push $(IMAGE)

clean: ## Remove local worker and amber images
	-docker rmi $(IMAGE) $(AMBER_IMAGE) || true

tag: ## Tag worker image with NEW_TAG: make tag NEW_TAG=v1.2.3
	@[ -n "$(NEW_TAG)" ] || { echo "Error: NEW_TAG not set" >&2; exit 1; }
	docker tag $(IMAGE) $(REGISTRY)/$(IMAGE_NAME):$(NEW_TAG)
	@echo "Tagged as $(REGISTRY)/$(IMAGE_NAME):$(NEW_TAG)"
