## Production deploymet

TODO: with helm in `helm/`

## Testing deployment

Single-user deployment with full JupyterHub (just dummy authentication), dashboard, volumes, notebooks.

**Quite different from previous version without JupyterHub!**

To set it up:
1. edit `config.yaml`, provide your values for at least `devNamespace`, `dashboard.hostname`
2. optionally, define also `dashboard.image`, go to `dashboard/` and build your images:
   - make build-stage
   - make push-dev
3. go to `helm-dev` and run `make notebook`; it starts quite normal Jupyter Hub with Jupyter Lab inside
4. open terminal there, and clone this git repository to become `/home/jovyan/mddash`
5. run `make upgrade`; it reconfigures the hub to start our GUI instead
7. run `make bash` to log in to the running container or `make logs` to see its logs

Now pointing a browser to https://YOUR_HOSTNAME/user/YOUR_USERNAME/dash/ yields the running dashboard.

All the stuff in `/home/jovyan/mddash/dashboard/api` can be edited (and pushed back to github eventually). Flask runs in debug mode, automatically reloading everything. 


 
