SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev

# IMAGE_TAG inherited from parent Makefile (exported), or computed here
ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
else
  IMAGE_TAG ?= $(shell date +%Y%m%d)-$(shell git rev-parse --short HEAD)
endif

config = $(if $(filter dev,$(ENV)),../config.dev.yaml,$(if $(filter minikube,$(ENV)),../config.minikube.yaml,../config.yaml))
package = $(shell yq .helm.package $(config))
namespace = $(shell yq '.namespace' $(config))
minikube_extra = $(if $(filter minikube,$(ENV)),-f $(chart_path)/values.minikube-overrides.yaml,)
chart_path := charts/mddash
values_file := -f $(chart_path)/values.yaml

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: render
render: ## Render Helm values template
	@echo "=== Rendering values for $(ENV) environment (tag=$(IMAGE_TAG)) ==="
	@IMAGE_TAG=$(IMAGE_TAG) gomplate -d config=$(config) \
		-f $(chart_path)/values.yaml.tmpl \
		-o $(chart_path)/values.yaml
	@echo "✓ Rendered $(chart_path)/values.yaml"

.PHONY: install
install: render update hub-templates ## Install Helm chart
	helm install $(package) $(chart_path) --namespace $(namespace) \
		$(values_file) $(minikube_extra) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/files/pre_spawn_hook.py

.PHONY: upgrade
upgrade: render hub-templates ## Upgrade Helm release
	helm upgrade $(package) $(chart_path) --namespace $(namespace) \
		$(values_file) $(minikube_extra) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/files/pre_spawn_hook.py

.PHONY: setup-minikube
setup-minikube: ENV := minikube
setup-minikube: ## One-time setup for minikube: kuberay, namespace, RBAC, and dummy secrets
	helm repo add kuberay https://ray-project.github.io/kuberay-helm/ || true
	helm install kuberay-operator kuberay/kuberay-operator || true
	kubectl create namespace $(namespace) --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f rbac/clusterrole.yaml
	kubectl create clusterrolebinding mddash-hub --clusterrole=mddash-hub \
		--serviceaccount=$(namespace):hub --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic oidc-credentials \
		--from-literal=client_id=dummy --from-literal=client_secret=dummy \
		-n $(namespace) --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic $(package)-s3-creds \
		--from-literal=S3_ACCESS_KEY=dummy --from-literal=S3_SECRET_KEY=dummy \
		-n $(namespace) --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic $(package)-mdrepo-credentials \
		--from-literal=client_id=dummy --from-literal=client_secret=dummy \
		-n $(namespace) --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic tuner-auth \
		--from-literal=user=dummy --from-literal=password=dummy \
		-n $(namespace) --dry-run=client -o yaml | kubectl apply -f -

.PHONY: install-minikube
install-minikube: ENV := minikube
install-minikube: render setup-minikube hub-templates ## Install on minikube for RBAC testing (skips chart dependency download)
	helm install $(package) $(chart_path) --namespace $(namespace) \
		$(values_file) -f $(chart_path)/values.minikube-overrides.yaml \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/files/pre_spawn_hook.py

.PHONY: deploy
deploy: upgrade ## Deploy (alias for upgrade)

.PHONY: update
update: ## Update Helm dependencies
	helm repo add kuberay https://ray-project.github.io/kuberay-helm/ || true
	helm install kuberay-operator kuberay/kuberay-operator || true
	rm -rf $(chart_path)/charts/*.tgz $(chart_path)/Chart.lock
	helm dependency update $(chart_path)

.PHONY: uninstall
uninstall: ## Uninstall Helm release
	helm uninstall $(package) --namespace $(namespace)
	helm uninstall kuberay-operator || true

.PHONY: uninstall-minikube
uninstall-minikube: ENV := minikube
uninstall-minikube: uninstall ## Uninstall minikube deployment and clean up namespace and RBAC
	kubectl delete namespace $(namespace) --ignore-not-found
	kubectl delete clusterrole mddash-hub clusterrolebinding mddash-hub --ignore-not-found

.PHONY: hub-templates
hub-templates: ## Create hub templates ConfigMap
	kubectl create configmap $(package)-custom-templates \
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

# ==================== ROLLBACK ====================

.PHONY: history
history: ## Show Helm release history
	@helm history $(package) --namespace $(namespace)

.PHONY: rollback
rollback: ## Rollback to previous revision (REVISION=N for specific)
	@if [ -n "$(REVISION)" ]; then \
		echo "Rolling back to revision $(REVISION)..."; \
		helm rollback $(package) $(REVISION) --namespace $(namespace); \
	else \
		echo "Rolling back to previous revision..."; \
		helm rollback $(package) --namespace $(namespace); \
	fi
	@echo "✓ Rollback complete"
	@$(MAKE) status
