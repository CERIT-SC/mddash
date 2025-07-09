ns = fida-ns
package = mddash


install:
	helm install $(package) . --namespace $(ns) --create-namespace

upgrade:
	helm dependency update .
	helm upgrade $(package) . --namespace $(ns)

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
