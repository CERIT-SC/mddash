SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev

ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
endif

config := $(if $(wildcard ../config.${ENV}.yaml),../config.${ENV}.yaml,../config.yaml)

package := $(shell yq -r .helm.package $(config))
namespace := $(shell yq -r '.namespace' $(config))
registry := $(shell yq -r '.registry' $(config))
chart_registry := $(registry)/charts
chart_path := charts/mddash
chart_name := mddash-jupyterhub
values_file := -f $(chart_path)/values.yaml
timeout := --timeout 10m

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
	@echo "Rendered $(chart_path)/values.yaml"

.PHONY: install
install: render update ## Install Helm chart
ifeq ($(ENV),prod)
	helm install $(package) oci://$(chart_registry)/$(chart_name) --version $(IMAGE_TAG) \
		--namespace $(namespace) $(values_file) $(timeout) --wait \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/files/pre_spawn_hook.py
else
	helm install $(package) $(chart_path) --namespace $(namespace) \
		$(values_file) $(timeout) --wait \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/files/pre_spawn_hook.py
endif

.PHONY: upgrade
upgrade: render ## Upgrade Helm release
ifeq ($(ENV),prod)
		helm upgrade --install $(package) oci://$(chart_registry)/$(chart_name) --version $(IMAGE_TAG) \
		--namespace $(namespace) $(values_file) $(timeout) --rollback-on-failure --wait \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/files/pre_spawn_hook.py
else
	helm upgrade --install $(package) $(chart_path) --namespace $(namespace) \
		$(values_file) $(timeout) --rollback-on-failure --wait \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/files/pre_spawn_hook.py
endif

.PHONY: deploy
deploy: upgrade ## Deploy (alias for upgrade)

.PHONY: update
update: update-deps ## Update local Helm chart dependencies

.PHONY: update-deps
update-deps: ## Update local Helm chart dependencies only
	mkdir -p $(chart_path)/charts
	helm package charts/mdrun-api \
		--version $$(yq -r '.version' charts/mdrun-api/Chart.yaml) \
		--app-version $$(yq -r '.appVersion' charts/mdrun-api/Chart.yaml) \
		--destination $(chart_path)/charts/
	helm package charts/tuner \
		--version $$(yq -r '.version' charts/tuner/Chart.yaml) \
		--app-version $$(yq -r '.appVersion' charts/tuner/Chart.yaml) \
		--destination $(chart_path)/charts/
	rm -rf $(chart_path)/Chart.lock
	helm dependency update $(chart_path)

.PHONY: uninstall
uninstall: ## Uninstall Helm release
	helm uninstall $(package) --namespace $(namespace)

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
	@echo "Rollback complete"
	@$(MAKE) status
