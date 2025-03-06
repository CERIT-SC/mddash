
j2s=pvc.yaml deployment.yaml ingress.yaml
yamls=service.yaml ${j2s}

ns=$(shell yq .devNamespace ../config.yaml)
pod=$(shell kubectl -n ${ns} get pods | grep ^mddash-dev | awk '{print $$1}')

${j2s}: %.yaml: %.yaml.j2 ../config.yaml
	jinja2 $< ../config.yaml -o $@


install: ${yamls}
	for f in ${yamls}; do kubectl -n ${ns} apply -f $$f; done

uninstall:
	kubectl -n ${ns} delete service/mddash-dev deployment.apps/mddash-dev   

	
log:
	kubectl -n ${ns} logs -f pod/${pod}
	
bash:
	kubectl -n ${ns} exec -ti pod/${pod} -- /bin/bash
