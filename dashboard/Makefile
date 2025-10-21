ENV ?= prod
IMAGE_TAG ?= latest
config ?= ../config.yaml

image = $(shell yq .dashboard.image ${config})
platform = --platform $(shell yq .dashboard.platform ${config})

ifeq ($(ENV),dev)
	TAG = dev
else
	TAG = $(IMAGE_TAG)
endif

.PHONY: build build-stage push build-dev push-dev

build: build-stage
	docker build ${platform} -t ${image}:${TAG} .

build-stage:
	docker build ${platform} --target build-stage -t ${image}:build-stage .

push: build
	docker push ${image}:${TAG}

build-dev: build
	docker build ${platform} -f Dockerfile.dev --build-arg IMAGE=${image}:${TAG} -t ${image}:${TAG}-dev .

push-dev: build-dev
	docker push ${image}:${TAG}-dev
