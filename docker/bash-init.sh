umask 022

alias ls='ls --color -p'
. /etc/bash_completion

PS1=''
PS1="$PS1\[\033[00;96m\]\u@$HOSTNAME:"
if [ "$USER" = 'root' ]
then
    PS1="$PS1\[\033[00;91m\]#"
    export HOME=/root
else
    PS1="$PS1\[\033[00;92m\]\$"
fi
PS1="$PS1\[\033[00;00m\] "

# pyenv setup
export PYENV_ROOT="/customization/pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
#eval "$(pyenv virtualenv-init -)"

# setup virtual env
VENV_NAME="cablewatch"
VENV_DIR="$PYENV_ROOT/versions/$VENV_NAME"

# Créer le venv si nécessaire
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtualenv '$VENV_NAME'..."
    pyenv virtualenv "$(pyenv version-name)" "$VENV_NAME"
fi

# Activer le venv automatiquement
if [ -d "$VENV_DIR" ]; then
    pyenv activate "$VENV_NAME"
fi
