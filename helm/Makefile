ENV ?= prod
config ?= ../config.yaml

package = $(shell yq .helm.package ${config})
chart_path = $(shell yq .helm.chartPath ${config})
namespace = $(shell yq '.$(ENV)Namespace' ${config})

VALUES_FILE = -f $(chart_path)/values.yaml

.PHONY: install upgrade deploy update uninstall hub-templates port-forward test status logs render


render:
	@echo "=== Rendering values for $(ENV) environment ==="
	@ENV=$(ENV) gomplate -d config=$(config) \
		-f $(chart_path)/values.yaml.tmpl \
		-o $(chart_path)/values.yaml
	@echo "✓ Rendered $(chart_path)/values.yaml"

install: render update hub-templates
	helm install $(package) $(chart_path) --namespace $(namespace) \
		$(VALUES_FILE) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/pre_spawn_hook.py

upgrade: render hub-templates
	helm upgrade $(package) $(chart_path) --namespace $(namespace) \
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
