# MD Dashboard JupyterHub Helm Chart

This Helm chart deploys JupyterHub with minimal configuration suitable for development and testing.

## Prerequisites

- Kubernetes cluster
- Helm 3.x
- kubectl configured to access your cluster

## Quick Start

1. **Get the kubeconfig from rancher and install it as a secret:**
   ```bash
   make kubeconfig
   ```

2. **Deploy JupyterHub:**
   ```bash
   make install
   ```

   This will:
   - Install the chart as `mddash` in the `fida-ns` namespace
   - Create the namespace if it doesn't exist

3. **Update an existing deployment:**
   ```bash
   make upgrade
   ```

   This will update dependencies and upgrade the release.

4. **Check deployment status:**
   ```bash
   make status
   ```

   Or manually:
   ```bash
   kubectl get pods -n fida-ns
   kubectl get svc -n fida-ns
   ```

   Wait for all pods to be in `Running` state before accessing JupyterHub.

5. **View logs:**
   ```bash
   make logs
   ```

## Configuration

The chart uses the official JupyterHub Helm chart as a dependency with the following default configuration:

- **Authentication**: Dummy authenticator (username: `admin`, password: `admin`)
- **Single User Image**: `jupyter/base-notebook:latest`
- **Default URL**: JupyterLab (`/lab`)
- **Ingress**: Disabled (access via port-forward or LoadBalancer)

## Accessing JupyterHub

After deployment, you can access JupyterHub using one of these methods:

### Method 1: Port-forwarding (Recommended for development)
```bash
kubectl port-forward svc/proxy-public 8080:80 -n fida-ns
```
Then open: http://localhost:8080

### Method 2: LoadBalancer (If supported by your cluster)
The `proxy-public` service is configured as a LoadBalancer by default. Check the external IP:
```bash
kubectl get svc proxy-public -n fida-ns
```

Wait for the `EXTERNAL-IP` to be assigned, then access JupyterHub using that IP.

### Method 3: NodePort (For local clusters like minikube)
If LoadBalancer is not available, you can change the service type to NodePort:

```yaml
# Add to values.yaml
jupyterhub:
  proxy:
    service:
      type: NodePort
```

Then get the node port:
```bash
kubectl get svc proxy-public -n fida-ns
```

### Method 4: Ingress (For production)
Enable ingress for production deployments:

```yaml
# Add to values.yaml
jupyterhub:
  ingress:
    enabled: true
    hosts:
      - your-domain.com
    annotations:
      kubernetes.io/ingress.class: nginx
      cert-manager.io/cluster-issuer: letsencrypt-prod
    tls:
      - hosts:
          - your-domain.com
        secretName: jupyterhub-tls
```

## Login

- Username: `admin`
- Password: `admin`

## Customization

To customize the configuration, edit `values.yaml` or provide your own values file:

```bash
helm install mddash . -f my-values.yaml --namespace fida-ns
```

### Common Customizations

**Change the single-user image:**
```yaml
jupyterhub:
  singleuser:
    image:
      name: your-registry/your-image
      tag: your-tag
```

**Enable ingress:**
```yaml
jupyterhub:
  ingress:
    enabled: true
    hosts:
      - host: mddash.dyn.cloud.e-infra.cz
    tls:
      - hosts:
          - mddash.dyn.cloud.e-infra.cz
        secretName: mddash-dyn-cloud-e-infra-cz-tls
```

**Change authentication:**
```yaml
jupyterhub:
  hub:
    config:
      JupyterHub:
        authenticator_class: generic-oauth
      GenericOAuthenticator:
        authorize_url: https://login.e-infra.cz/oidc/authorize
        token_url: https://login.e-infra.cz/oidc/token
        userdata_url: https://login.e-infra.cz/oidc/userinfo
        oauth_callback_url: https://mddash.dyn.cloud.e-infra.cz/hub/oauth_callback
        client_id: <your-client-id>
        client_secret: <your-client-secret>
        userdata_params:
          state: state
        scope:
          - openid
          - profile
          - email
        username_key: preferred_username
```

## Cleanup

To remove the deployment:
```bash
make uninstall
```

## Troubleshooting

### Check pod status
```bash
kubectl get pods -n fida-ns
kubectl describe pod <pod-name> -n fida-ns
```

### Check logs
```bash
kubectl logs -f deployment/hub -n fida-ns
kubectl logs -f deployment/proxy -n fida-ns
```

### Check services
```bash
kubectl get svc -n fida-ns
kubectl describe svc proxy-public -n fida-ns
```

### Common issues
- **Pods stuck in Pending**: Check node resources and storage
- **External IP stuck in Pending**: Your cluster might not support LoadBalancer
- **Can't access JupyterHub**: Check if pods are running and service is accessible

## Next Steps

- Replace the dummy authenticator with a proper authentication method
- Configure persistent storage for user data
- Set up proper ingress with TLS
- Replace the default single-user image with your custom image containing your MD Dashboard tools
