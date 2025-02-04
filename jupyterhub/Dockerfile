ARG JUPYTERHUB_VERSION
FROM quay.io/jupyterhub/jupyterhub:$JUPYTERHUB_VERSION

RUN pip install dockerspawner jupyter

# IMPORTANT: only for debugging, make sure to change the authentication method in porduction
# Create a demo user
RUN useradd -m -s /bin/bash admin && echo "admin:123456" | chpasswd

COPY . /srv/jupyterhub/

# HEALTHCHECK CMD curl --fail http://localhost:8000/hub/health || exit 1
# HEALTHCHECK CMD exit 0
CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
