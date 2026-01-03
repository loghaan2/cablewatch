FROM python:3.13-slim

ARG UID=1000
ARG GID=1000
ARG USER=cablewatch-user
ARG PROJECT_DIR=/home/cablewatch-user/cablewatch

RUN groupadd -g ${GID} ${USER} && useradd -m -u ${UID} -g ${GID} ${USER}

ENV TZ=Europe/Paris

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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN npm install -g wscat

USER ${USER}
WORKDIR /customization

ENV PYENV_ROOT="/customization/pyenv"
RUN git clone https://github.com/pyenv/pyenv.git "$PYENV_ROOT"
RUN git clone https://github.com/pyenv/pyenv-virtualenv.git "$PYENV_ROOT/plugins/pyenv-virtualenv"

COPY bash-init.sh .

WORKDIR ${PROJECT_DIR}
CMD ["bash", "--noprofile", "--init-file", "/customization/bash-init.sh"]
