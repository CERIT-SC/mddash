ENV ?= prod
IMAGE_TAG ?= latest
IMAGE_NAME = cerit.io/xkrasa/mdrun-api

ifeq ($(ENV),dev)
	TAG = dev
else
	TAG = $(IMAGE_TAG)
endif

build:
	docker build -t $(IMAGE_NAME):$(TAG) .

push: build
	docker push $(IMAGE_NAME):$(TAG)

clean:
	docker rmi $(IMAGE_NAME):$(TAG) || true

.PHONY: build push clean
