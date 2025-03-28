config=../config.yaml
ns=$(shell yq .devNamespace ${config})
image=$(shell yq .dashboard.image.name ${config})
tag=$(shell yq .dashboard.image.tag ${config})
user=$(shell yq .dashboard.user ${config})
dashboard_host=$(shell yq .dashboard.hostname ${config})
dashboard_tls_secret=$(shell yq .dashboard.hostname ${config} | tr . -)
password=$(shell yq .dashboard.password ${config} | tr . -)


install upgrade:
	helm $@ mddash -n ${ns} jupyterhub/jupyterhub -f values.yaml \
		--set hub.config.notebookImage=${dashboard_image} \
		--set ingress.hosts={${dashboard_host}} \
		--set 'ingress.tls[0].hosts={${dashboard_host}}' \
		--set 'ingress.tls[0].secretName=${dashboard_tls_secret}' \
		--set hub.config.DummyAuthenticator.password=${password} \
		--set singleuser.image.name=${image} \
		--set singleuser.image.tag=${tag} \
		--set singleuser.cmd='/start.sh'
#		--set singleuser.cmd='{sleep,365d}'

uninstall:
	helm uninstall mddash -n ${ns}


ntbcmd?=install
notebook:
	helm ${ntbcmd} mddash -n ${ns} jupyterhub/jupyterhub -f values.yaml \
		--set hub.config.notebookImage=${dashboard_image} \
		--set ingress.hosts={${dashboard_host}} \
		--set 'ingress.tls[0].hosts={${dashboard_host}}' \
		--set 'ingress.tls[0].secretName=${dashboard_tls_secret}' \
		--set hub.config.DummyAuthenticator.password=${password} \

bash:
	kubectl -n ${ns} exec -ti pod/jupyter-${user} -- bash

logs:
	kubectl -n ${ns} logs -f pod/jupyter-${user}
