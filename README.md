## Production deploymet

TODO: with helm in `helm/`

## Testing deployment

Everything below the authentication layer, i.e. the dashboard itself, volumes and notebooks.

To set it up:
1. edit `config.yaml`, provide your values for at least `devNamespace`, `dashboard.hostname`, `dashboard.user`
2. optionally, define also `dashboard.devImage`, go to `dashboard/` and build your images:
   - `make build-stage`
   - `make push-dev`
3. go to `k8s-dev` and run `make install`; it starts the dashboard container which runs just `sleep 365d`
4. run `make start`; this runs `/start.sh` in the container in foreground to see all the logs

Now pointing a browser to https://YOUR_HOSTNAME/user/YOUR_USERNAME/dash/ yields the running dashboard.
