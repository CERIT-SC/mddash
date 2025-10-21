ENV ?= prod
IMAGE_TAG ?= $(if $(filter dev,$(ENV)),dev,latest)
CONFIG = config.yaml
NAMESPACE = $(shell yq '.$(ENV)Namespace' $(CONFIG))

.PHONY: help build push deploy all clean status logs build-dashboard build-notebook build-mdrun-api push-dashboard push-notebook push-mdrun-api

help:
	@echo "Usage: make <target> ENV=dev|prod"
	@echo ""
	@echo "Targets:"
	@echo "  build                - Build all images"
	@echo "  build-dashboard      - Build dashboard only"
	@echo "  build-notebook       - Build notebook only"
	@echo "  build-mdrun-api      - Build mdrun-api only"
	@echo "  push                 - Push all images"
	@echo "  push-dashboard       - Push dashboard only"
	@echo "  push-notebook        - Push notebook only"
	@echo "  push-mdrun-api       - Push mdrun-api only"
	@echo "  deploy               - Deploy via Helm"
	@echo "  all                  - Build, push, deploy"
	@echo "  status               - Show deployment status"
	@echo "  logs                 - Show logs"
	@echo ""
	@echo "Current: ENV=$(ENV), TAG=$(IMAGE_TAG), NS=$(NAMESPACE)"

build: build-dashboard build-notebook build-mdrun-api

build-dashboard:
	@$(MAKE) -C dashboard build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

build-notebook:
	@$(MAKE) -C notebook build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

build-mdrun-api:
	@$(MAKE) -C mdrun-api build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

push: push-dashboard push-notebook push-mdrun-api

push-dashboard:
	@$(MAKE) -C dashboard push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

push-notebook:
	@$(MAKE) -C notebook push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

push-mdrun-api:
	@$(MAKE) -C mdrun-api push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

deploy:
	@$(MAKE) -C helm deploy ENV=$(ENV) NAMESPACE=$(NAMESPACE)

all: build push deploy

clean:
	@$(MAKE) -C helm uninstall ENV=$(ENV) NAMESPACE=$(NAMESPACE)

status:
	@$(MAKE) -C helm status ENV=$(ENV) NAMESPACE=$(NAMESPACE)

logs:
	@$(MAKE) -C helm logs ENV=$(ENV) NAMESPACE=$(NAMESPACE)
