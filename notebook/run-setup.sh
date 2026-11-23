#!/bin/bash
set -euo pipefail
# Headless setup run (Kubernetes Job): the notebook pod's env, then the executor instead of Jupyter.
# start.sh has already run before-notebook.d, so the Binder env is installed when this starts.

# shellcheck source=activate-env.sh
source /usr/local/bin/activate-env.sh

exec mddash-run-notebook "$@"
