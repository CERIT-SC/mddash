FROM hairyhenderson/gomplate:v5.2.0 AS gomplate

FROM mcr.microsoft.com/devcontainers/base:ubuntu26.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends make yq \
 && rm -rf /var/lib/apt/lists/*

COPY --from=gomplate /gomplate /usr/local/bin/gomplate

WORKDIR /workspaces/mddash

USER vscode

RUN printf '\nif ! kubectl config current-context >/dev/null 2>&1; then\n  echo "⚠️  No kubeconfig detected. Copy your kubeconfig to ~/.kube/config or set KUBECONFIG."\nfi\n' >> /home/vscode/.bashrc
