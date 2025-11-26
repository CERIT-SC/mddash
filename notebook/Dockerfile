FROM quay.io/jupyter/base-notebook:latest

USER root

RUN apt update && apt install -y curl vim && apt clean && rm -rf /var/lib/apt/lists/*

# Create group 1000 for jovyan (K8s fsGroup compatibility)
RUN groupadd -f -g 1000 jovyan && usermod -aG jovyan jovyan

RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && install -m 755 kubectl /usr/local/bin 
COPY --chown=1000:1000 gmx /usr/local/bin/gmx

USER 1000
COPY requirements.txt /tmp
RUN pip3 install -r /tmp/requirements.txt

COPY --chown=1000:1000 *.ipynb /home/jovyan/
