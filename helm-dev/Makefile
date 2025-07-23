ns = fida-ns
package = mddash
kubeconfig_path = ../private/kuba-cluster.yaml

install:
# 	helm repo add kuberay https://ray-project.github.io/kuberay-helm/ || true
# 	helm install kuberay-operator kuberay/kuberay-operator || true
# 	helm dependency update .
	helm install $(package) . --namespace $(ns) --create-namespace \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=pre_spawn_hook.py

upgrade:
	helm upgrade $(package) . --namespace $(ns) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=pre_spawn_hook.py

update:
	helm dependency update .

uninstall:
	helm uninstall $(package) --namespace $(ns)

port-forward:
	@echo "Access the dashboard at http://localhost:8000"
	kubectl port-forward svc/proxy-public 8000:80 -n $(ns)

test:
	helm template $(package) . --debug --namespace $(ns)

status:
	@echo "=== Helm Release Status ==="
	helm status $(package) --namespace $(ns)
	@echo "\n=== Pod Status ==="
	kubectl get pods -n $(ns)
	@echo "\n=== Service Status ==="
	kubectl get svc -n $(ns)

logs:
	kubectl logs -f deployment/hub -n $(ns)
