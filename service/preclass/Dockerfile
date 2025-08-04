FROM ubuntu:20.04

# COPY ./docker/http.sources.list /etc/apt/sources.list

ENV DEBIAN_FRONTEND=noninteractive

RUN apt clean && apt autoclean && apt update

RUN apt install curl -y && curl www.google.com

RUN apt install ssl-cert -y

# COPY ./docker/sources.list /etc/apt/sources.list

RUN apt clean && apt autoclean && apt update


RUN apt-get install -y libreoffice

RUN apt-get install -y fonts-noto-cjk fonts-droid-fallback fonts-wqy-zenhei fonts-wqy-microhei


RUN fc-cache -fv

WORKDIR /data
