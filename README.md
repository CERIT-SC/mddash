# MDDash

Molecular Dynamics simulation dashboard with JupyterHub integration.

## CI/CD Setup

1. **Add GitHub secrets** (Settings → Secrets):
   - `REGISTRY_USERNAME` - Container registry user
   - `REGISTRY_PASSWORD` - Container registry password  
   - `KUBECONFIG` - Your kubeconfig base64 encoded: `cat ~/.kube/config | base64 -w 0`
   - `OAUTH_CLIENT_ID` - OAuth client ID for authentication
   - `OAUTH_CLIENT_SECRET` - OAuth client secret

2. **Push to deploy**:
   - Push to `dev` → deploys to dev environment
   - Push to `master` → deploys to production

All secrets are automatically created in the namespace during deployment.

## Configuration

Edit `config.yaml`

## Local Commands

```bash
make build ENV=dev    # Build images
make all ENV=dev      # Build, push, deploy
make status ENV=dev   # Check status
make help             # Show all commands
```
