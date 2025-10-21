ENV ?= prod
IMAGE_TAG ?= latest
config ?= ../config.yaml

image = $(shell yq .notebook.image ${config})
platform = --platform $(shell yq .notebook.platform ${config})

ifeq ($(ENV),dev)
	TAG = dev
else
	TAG = $(IMAGE_TAG)
endif

.PHONY: build push

build:
	docker build ${platform} -t ${image}:${TAG} .

push: build
	docker push ${image}:${TAG}
