ns = md-dashboard-ns
package = mddash
chart_path = charts/mddash
kubeconfig_path = ../private/kuba-cluster.yaml

install: update
# 	helm repo add kuberay https://ray-project.github.io/kuberay-helm/ || true
# 	helm install kuberay-operator kuberay/kuberay-operator || true
	helm install $(package) $(chart_path) --namespace $(ns) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/pre_spawn_hook.py

upgrade:
	helm upgrade $(package) $(chart_path) --namespace $(ns) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=$(chart_path)/pre_spawn_hook.py

update:
	helm dependency update $(chart_path)

uninstall:
	helm uninstall $(package) --namespace $(ns)

kubeconfig:
	kubectl create secret generic mddash-kubeconfig-secret \
		--from-file=config=$(kubeconfig_path) \
		-n $(ns)

port-forward:
	kubectl port-forward svc/proxy-public 8000:80 -n $(ns)

test:
	helm template $(package) $(chart_path) --debug --namespace $(ns)

status:
	@echo "=== Helm Release Status ==="
	helm status $(package) --namespace $(ns)
	@echo "\n=== Pod Status ==="
	kubectl get pods -n $(ns)
	@echo "\n=== Service Status ==="
	kubectl get svc -n $(ns)

logs:
	kubectl logs -f deployment/hub -n $(ns)
