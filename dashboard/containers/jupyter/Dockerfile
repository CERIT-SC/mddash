FROM quay.io/jupyterhub/singleuser:5

USER 1000

EXPOSE 8889

ENTRYPOINT ["jupyterhub-singleuser"]
CMD ["--ip=0.0.0.0", "--port=8889", "--allow-root", "--notebook-dir=/home/jovyan"]
