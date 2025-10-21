# MDDash CI/CD - Single source of truth: config.yaml
ENV ?= prod
IMAGE_TAG ?= $(if $(filter dev,$(ENV)),dev,latest)
CONFIG = config.yaml
NAMESPACE = $(shell yq '.$(ENV)Namespace' $(CONFIG))

.PHONY: help build push deploy all clean status logs

help:
	@echo "Usage: make <target> ENV=dev|prod"
	@echo ""
	@echo "Targets:"
	@echo "  build   - Build all images"
	@echo "  push    - Push all images"
	@echo "  deploy  - Deploy via Helm"
	@echo "  all     - Build, push, deploy"
	@echo "  status  - Show deployment status"
	@echo "  logs    - Show logs"
	@echo ""
	@echo "Current: ENV=$(ENV), TAG=$(IMAGE_TAG), NS=$(NAMESPACE)"

build:
	@$(MAKE) -C dashboard build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)
	@$(MAKE) -C notebook build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)
	@$(MAKE) -C mdrun-api build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

push:
	@$(MAKE) -C dashboard push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)
	@$(MAKE) -C notebook push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)
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
