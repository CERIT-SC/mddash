FROM node:21 as build-stage

WORKDIR /usr/src/app
COPY ./dash .

RUN npm install --force
RUN npm run build

FROM alpine:3.21

RUN apk add py3-flask

COPY ./api /opt/api
COPY ./start.sh /start.sh

# Dash frontend app
COPY --from=build-stage /usr/src/app/dist /opt/dash

# User environment

RUN adduser --disabled-password --uid 1000 jovyan

# TODO: PVC
#RUN mkdir -p /home/jovyan/work/data
#RUN ln -s /home/jovyan/work/data /home/jovyan/work/experiment
#RUN chown -R jovyan:users /home/jovyan/


CMD ["/start.sh" ]

# docker build -t cerit.io/ljocha/mddash . && docker push cerit.io/ljocha/mddash
