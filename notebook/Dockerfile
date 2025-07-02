FROM quay.io/jupyter/base-notebook:latest

USER root

RUN apt update && apt install -y curl vim && apt clean && rm -rf /var/lib/apt/lists/*

RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && install -m 755 kubectl /usr/local/bin 
COPY --chown=jovyan gmx /usr/local/bin/gmx

USER 1000
RUN pip3 install GromacsWrapper





