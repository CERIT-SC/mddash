SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= prod

config := ../config.yaml
package := $(shell yq .helm.package $(config))
chart_path := $(shell yq .helm.chartPath $(config))
namespace := $(shell yq '.$(ENV)Namespace' $(config))
values_file := -f $(chart_path)/values.yaml

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: render
render: ## Render Helm values template
	@echo "=== Rendering values for $(ENV) environment ==="
	@ENV=$(ENV) gomplate -d config=$(config) \
		-f $(chart_path)/values.yaml.tmpl \
		-o $(chart_path)/values.yaml
	@echo "✓ Rendered $(chart_path)/values.yaml"

.PHONY: install
install: render update hub-templates ## Install Helm chart
	helm install $(package) $(chart_path) --namespace $(namespace) \
		$(values_file) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/pre_spawn_hook.py

.PHONY: upgrade
upgrade: render hub-templates ## Upgrade Helm release
	helm upgrade $(package) $(chart_path) --namespace $(namespace) \
		$(values_file) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/pre_spawn_hook.py

.PHONY: deploy
deploy: upgrade ## Deploy (alias for upgrade)

.PHONY: update
update: ## Update Helm dependencies
	helm repo add jupyterhub https://hub.jupyter.org/helm-chart/ 2>/dev/null || true
	helm repo add minio https://operator.min.io/ 2>/dev/null || true
	helm repo update
	rm -rf $(chart_path)/charts/*.tgz $(chart_path)/Chart.lock
	helm dependency update $(chart_path)

.PHONY: uninstall
uninstall: ## Uninstall Helm release
	helm uninstall $(package) --namespace $(namespace)

.PHONY: hub-templates
hub-templates: ## Create hub templates ConfigMap
	kubectl create configmap mddash-custom-templates \
		--from-file=$(chart_path)/files/hub-templates \
		-n $(namespace) --dry-run=client -o yaml | kubectl apply -f -

.PHONY: port-forward
port-forward: ## Forward port 8000 to proxy-public service
	kubectl port-forward svc/proxy-public 8000:80 -n $(namespace)

.PHONY: test
test: ## Test Helm template rendering
	helm template $(package) $(chart_path) --debug --namespace $(namespace) $(values_file)

.PHONY: status
status: ## Show deployment status
	@echo "=== Helm Release Status ==="
	helm status $(package) --namespace $(namespace)
	@echo ""
	@echo "=== Pod Status ==="
	kubectl get pods -n $(namespace)
	@echo ""
	@echo "=== Service Status ==="
	kubectl get svc -n $(namespace)

.PHONY: logs
logs: ## Show hub deployment logs
	kubectl logs -f deployment/hub -n $(namespace)
