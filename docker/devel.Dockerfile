FROM python:3.13-slim

ARG UID=1000
ARG GID=1000
ARG USER=cablewatch-user
ARG PROJECT_DIR=/home/cablewatch-user/cablewatch

RUN groupadd -g ${GID} ${USER} && useradd -m -u ${UID} -g ${GID} ${USER}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tzdata \
        bash-completion \
        ffmpeg \
        bash \
        curl \
        git \
        nano \
        mc \
        make \
        npm \
        emacs \
        tree \
        unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g wscat

RUN curl https://install.duckdb.org/v1.4.3/duckdb_cli-linux-amd64.zip | funzip > /usr/local/bin/duckdb
RUN chmod +x /usr/local/bin/duckdb

USER ${USER}
WORKDIR /customization

ENV PYENV_ROOT="/customization/pyenv"
RUN git clone https://github.com/pyenv/pyenv.git "$PYENV_ROOT"
RUN git clone https://github.com/pyenv/pyenv-virtualenv.git "$PYENV_ROOT/plugins/pyenv-virtualenv"

COPY bash-init.sh .

WORKDIR ${PROJECT_DIR}
CMD ["bash", "--noprofile", "--init-file", "/customization/bash-init.sh"]
