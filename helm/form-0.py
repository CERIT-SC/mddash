from traitlets import Unicode
from kubespawner import KubeSpawner

class SillySpawner(KubeSpawner):
  form_template = Unicode("")

  async def get_options_form(self):
    return self.form_template


c.JupyterHub.spawner_class = SillySpawner
c.MappingKernelManager.cull_idle_timeout = 259200
c.MappingKernelManager.cull_connected = False
c.MappingKernelManager.cull_busy = False
c.NotebookApp.shutdown_no_activity_timeout = 259200

