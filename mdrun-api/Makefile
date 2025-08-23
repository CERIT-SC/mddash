IMAGE_NAME = cerit.io/xkrasa/mdrun-api
TAG = latest

build:
	docker build -t $(IMAGE_NAME):$(TAG) .

push:
	docker push $(IMAGE_NAME):$(TAG)

clean:
	docker rmi $(IMAGE_NAME):$(TAG) || true

.PHONY: build build-minikube push clean
