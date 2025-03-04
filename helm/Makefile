ns?=gmxhub-ns
dashboard_image?=$(shell cat ../IMAGE)


install:
	helm install mddash -n ${ns} jupyterhub/jupyterhub -f values.yaml \
		--set hub.config.GenericOAuthenticator.client_secret=${shell cat client_secret} \
		--set hub.config.notebookImage=${dashboard_image} \
		--set-file hub.extraConfig.form-0=form-0.py \
		--set-file hub.extraConfig.pre-spawn-hook=pre-spawn-hook.py

uninstall:
	helm uninstall mddash -n ${ns}


