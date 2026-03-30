FROM mcr.microsoft.com/devcontainers/base:ubuntu

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    bash \
    git \
    openssh-client \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    make \
    yq \
 && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 # Docker, kubectl, helm are installed by the features in devcontainer.json
 # Install gomplate
 && GOMPLATE_VERSION=4.3.3 \
 && curl -fsSL -o /usr/local/bin/gomplate https://github.com/hairyhenderson/gomplate/releases/download/v${GOMPLATE_VERSION}/gomplate_linux-amd64 \
 && chmod +x /usr/local/bin/gomplate

WORKDIR /workspaces/mddash

USER vscode

# Create a virtual environment in the default non-root user's home so it is writable
RUN python3 -m venv /home/vscode/.venv
ENV PATH="/home/vscode/.venv/bin:$PATH"

# Notify user to set up kubeconfig for local kubectl access (the deployed app uses in-cluster config)
RUN echo '\n# Notify if kubeconfig is missing\nif ! kubectl config current-context >/dev/null 2>&1; then\n  echo "⚠️  No kubeconfig detected. Copy your kubeconfig to ~/.kube/config or set KUBECONFIG."\n  echo "    Example: mkdir -p ~/.kube && cp /path/to/your/kubeconfig ~/.kube/config"\nfi\n' >> /home/vscode/.bashrc
