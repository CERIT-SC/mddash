# MDDash

Molecular Dynamics simulation dashboard with JupyterHub integration.

## CI/CD Setup

1. **Add GitHub secrets** (Settings → Secrets):
   - `REGISTRY_USERNAME` - Container registry user
   - `REGISTRY_PASSWORD` - Container registry password  
   - `KUBECONFIG` - Your kubeconfig base64 encoded: `cat ~/.kube/config | base64 -w 0`

2. **Create dev branch**:
   ```bash
   git checkout -b dev
   git push origin dev
   ```

3. **Push to deploy**:
   - Push to `dev` → deploys to dev environment
   - Push to `master` → deploys to production

## Configuration

Edit `config.yaml`:

```yaml
devNamespace: fida-ns
prodNamespace: gmxhub-ns
dashboard:
  image: cerit.io/xkrasa/mddash
```

## Local Commands

```bash
make build ENV=dev    # Build images
make all ENV=dev      # Build, push, deploy
make status ENV=dev   # Check status
make help             # Show all commands
```
