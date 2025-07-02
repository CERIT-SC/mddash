config?=../config.yaml
image?=${shell yq .notebook.image ${config} }

build:
	docker build --platform linux/amd64 -t ${image} .

push:
	docker push ${image}
