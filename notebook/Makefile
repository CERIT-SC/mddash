ENV ?= prod
IMAGE_TAG ?= latest
config ?= ../config.yaml

image = $(shell yq .notebook.image ${config})

ifeq ($(ENV),dev)
	TAG = dev
else
	TAG = $(IMAGE_TAG)
endif

build:
	docker build --platform linux/amd64 -t ${image}:${TAG} .

push: build
	docker push ${image}:${TAG}
