FROM node:21 as build-stage

WORKDIR /usr/src/app
COPY ./dash .

RUN npm install --force
RUN npm run build

FROM quay.io/jupyter/base-notebook:latest

USER root

# Dash frontend app
COPY --from=build-stage /usr/src/app/dist /var/www/dash

# Nginx
RUN apt-get update
RUN apt-get install -y nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Jupyter
RUN pip install jupyter jupyter-server-proxy
RUN mkdir -p /home/jovyan/.jupyter
COPY jupyter_server_config.py /home/jovyan/.jupyter/jupyter_server_config.py
RUN chown -R jovyan:users /home/jovyan/.jupyter/

# Flask API
COPY ./api /var/www/api
RUN pip install -r /var/www/api/requirements.txt

# User environment
RUN mkdir -p /home/jovyan/work/data
RUN ln -s /home/jovyan/work/data /home/jovyan/work/experiment
RUN chown -R jovyan:users /home/jovyan/

# Expose the ports
EXPOSE 3000 5000 8888

# For some FUCKING reason, the start script cannot be executed as root, so i adsfjkhilgzggzgzgzgzgzgzgzgMSABV Xabv abv abv xabv xabv xabv xabv &
RUN echo "jovyan ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

COPY start.sh /start.sh
CMD ["/start.sh"]

# docker build -t fair-md-dash -f Dockerfile .
# docker run --name my-dashboard -p 3000:3000 -p 5000:5000 -p 8888:8888 fair-md-dash
