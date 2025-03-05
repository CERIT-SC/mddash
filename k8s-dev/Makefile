
j2s=deployment.yaml ingress.yaml
yamls=service.yaml ${j2s}

${j2s}: %.yaml: %.yaml.j2 ../config.yaml
	jinja2 $< ../config.yaml -o $@


install: ${yamls}
	cat ${yamls} | kubectl apply -f -
	
