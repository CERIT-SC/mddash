#!/bin/bash

# inject base path
echo "injecting base path"
BASE_PATH="/user/${JUPYTERHUB_USER}/dash"
sudo find /var/www/dash -type f -exec sed -i "s|/__BASE_PATH__|${BASE_PATH}|g" {} +

# Jupyter Notebook
echo "starting jupyter notebook"
/usr/local/bin/start-notebook.py --config=/home/jovyan/.jupyter/jupyter_server_config.py &

# Nginx (frontend)
echo "starting nginx"
sudo nginx -g 'daemon off;' &

# API
echo "starting API"
python /var/www/api/main.py
