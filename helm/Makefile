ns = fida-ns
package = mddash

install:
	helm repo add kuberay https://ray-project.github.io/kuberay-helm/ || true
	helm install kuberay-operator kuberay/kuberay-operator || true
	helm dependency update .
	helm install $(package) . --namespace $(ns) --create-namespace \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=pre_spawn_hook.py

upgrade:
	helm upgrade $(package) . --namespace $(ns) \
		--set-file jupyterhub.hub.extraConfig.pre-spawn-hook=pre_spawn_hook.py

update:
	helm dependency update .

uninstall:
	helm uninstall $(package) --namespace $(ns)

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
