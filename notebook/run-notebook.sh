#!/bin/bash
set -euo pipefail
# Runs the full notebook lifecycle: start Jupyter, then self-terminate the pod on exit.

start-with-binder.sh "$@" || true

# After Jupyter exits (idle shutdown or crash), delete the pod so the gmx sidecar
# and all reserved resources are freed. MY_POD_NAME is injected via Downward API.
if [[ -n "${MY_POD_NAME:-}" ]]; then
    kubectl delete pod "$MY_POD_NAME" --grace-period=30 2>/dev/null || true
fi
