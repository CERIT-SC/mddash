
config?=../config.yaml

j2s=pvc-data.yaml deployment.yaml ingress.yaml rolebinding.yaml
yamls=service.yaml pvc-home.yaml role.yaml ${j2s}

ns=$(shell yq .devNamespace ${config})
pod=$(shell kubectl -n ${ns} get pods | grep ^mddash-dev | awk '{print $$1}')

${j2s}: %.yaml: %.yaml.j2 ${config}
	jinja2 $< ${config} -o $@


install: ${yamls}
	for f in ${yamls}; do kubectl -n ${ns} apply -f $$f; done

uninstall:
	kubectl -n ${ns} delete service/mddash-dev deployment.apps/mddash-dev

clean:
	kubectl -n ${ns} delete ingress mddash-dev || true
	kubectl -n ${ns} delete pods --all || true
	kubectl -n ${ns} delete pvc --all || true
	rm -f ${j2s}

start:
	kubectl -n ${ns} exec -ti pod/${pod} -- /start.sh

log:
	kubectl -n ${ns} logs -f pod/${pod}

bash:
	kubectl -n ${ns} exec -ti pod/${pod} -- /bin/bash

diff:
	kubectl -n ${ns} exec pod/${pod} -- bash -c "cd /home/jovyan/mddash && git diff"

patch:
	kubectl -n ${ns} exec pod/${pod} -- bash -c "cd /home/jovyan/mddash && git diff" | (cd .. && patch -p1)

copy-api:
	(cd ../dashboard/api/ && tar cf - . ) | kubectl exec -i ${pod} -- bash -c "cd /opt/api && tar xvf -"
