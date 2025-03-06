image=$(shell yq .dashboard.image ../config.yaml)
devImage=$(shell yq .dashboard.devImage ../config.yaml)

build:
	docker build -t ${image} . 

build-stage:
	docker build --target build-stage -t ${image} . 

push: build
	docker push ${image}


build-dev: build
	docker build -f Dockerfile.dev --build-arg IMAGE=${image} -t ${devImage} . 

push-dev: build-dev
	docker push ${devImage}
