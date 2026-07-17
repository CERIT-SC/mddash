FROM hairyhenderson/gomplate:v5.2.0 AS gomplate
FROM rhysd/actionlint:v1.7.12 AS actionlint
FROM mikefarah/yq:4.53.3 AS yq

FROM mcr.microsoft.com/devcontainers/base:ubuntu26.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends make \
 && rm -rf /var/lib/apt/lists/*

COPY --from=gomplate /gomplate /usr/local/bin/gomplate
COPY --from=actionlint /usr/local/bin/actionlint /usr/local/bin/actionlint
COPY --from=yq /usr/bin/yq /usr/local/bin/yq

WORKDIR /workspaces/mddash

USER vscode

RUN printf '\nif ! kubectl config current-context >/dev/null 2>&1; then\n  echo "⚠️  No kubeconfig detected. Copy your kubeconfig to ~/.kube/config or set KUBECONFIG."\nfi\n' >> /home/vscode/.bashrc
