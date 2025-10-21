ENV ?= prod
NAMESPACE ?= md-dashboard-ns
config ?= ../config.yaml

package = $(shell yq .helm.package ${config})
chart_path = $(shell yq .helm.chartPath ${config})
kubeconfig_path = $(shell yq .helm.kubeconfigPath ${config})

ifeq ($(ENV),dev)
	VALUES_FILE = -f $(chart_path)/values.yaml -f $(chart_path)/values.dev.yaml
else
	VALUES_FILE = -f $(chart_path)/values.yaml
endif

install: update hub-templates
	helm install $(package) $(chart_path) --namespace $(NAMESPACE) \
		$(VALUES_FILE) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/pre_spawn_hook.py

upgrade: hub-templates
	helm upgrade $(package) $(chart_path) --namespace $(NAMESPACE) \
		$(VALUES_FILE) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/pre_spawn_hook.py

deploy: upgrade

update:
	helm dependency update $(chart_path)

uninstall:
	helm uninstall $(package) --namespace $(NAMESPACE)

hub-templates:
	kubectl create configmap mddash-custom-templates \
		--from-file=$(chart_path)/files/hub-templates \
		-n $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -

kubeconfig:
	kubectl create secret generic mddash-kubeconfig-secret \
		--from-file=config=$(kubeconfig_path) \
		-n $(NAMESPACE)

port-forward:
	kubectl port-forward svc/proxy-public 8000:80 -n $(NAMESPACE)

test:
	helm template $(package) $(chart_path) --debug --namespace $(NAMESPACE) $(VALUES_FILE)

status:
	@echo "=== Helm Release Status ==="
	helm status $(package) --namespace $(NAMESPACE)
	@echo "\n=== Pod Status ==="
	kubectl get pods -n $(NAMESPACE)
	@echo "\n=== Service Status ==="
	kubectl get svc -n $(NAMESPACE)

logs:
	kubectl logs -f deployment/hub -n $(NAMESPACE)
