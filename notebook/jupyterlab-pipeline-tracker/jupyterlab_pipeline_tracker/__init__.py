"""JupyterLab Pipeline Tracker extension."""

# ruff:file-ignore[non-empty-init-module]

__version__ = "0.1.0"


def _jupyter_labextension_paths() -> list[dict[str, str]]:
    return [
        {
            "src": "labextension",
            "dest": "jupyterlab-pipeline-tracker",
        }
    ]
