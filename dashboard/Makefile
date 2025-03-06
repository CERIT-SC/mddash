image=$(shell yq .dashboard.image ../config.yaml)
devImage=$(shell yq .dashboard.devImage ../config.yaml)

platform=--platform linux/amd64

build: build-stage
	docker build ${platform} -t ${image} . 

build-stage:
	docker build ${platform} --target build-stage -t ${image} . 

push: build
	docker push ${image}


build-dev: build
	docker build ${platform} -f Dockerfile.dev --build-arg IMAGE=${image} -t ${devImage} . 

push-dev: build-dev
	docker push ${devImage}
