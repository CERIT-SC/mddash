ENV ?= prod
IMAGE_TAG ?= latest
config ?= ../config.yaml

image = $(shell yq .mdrunApi.image ${config})
platform = --platform $(shell yq .mdrunApi.platform ${config})

ifeq ($(ENV),dev)
	TAG = dev
else
	TAG = $(IMAGE_TAG)
endif

.PHONY: build push clean

build:
	docker build ${platform} -t ${image}:${TAG} .

push: build
	docker push ${image}:${TAG}

clean:
	docker rmi ${image}:${TAG} || true
