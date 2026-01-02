#!/usr/bin/env python3

import sys
import os
import pathlib


PROJECT_DIR=pathlib.Path(__file__).parent.parent


def main():
    cmd = [
        'docker', 'run',
        '-v', '/home:/home',
        '-v', f'{PROJECT_DIR}/.cache/docker-volumes/pyenv-versions:/customization/pyenv/versions',
        '--user', f'{os.getuid()}:{os.getgid()}',
        '-it', '--rm',
        '--hostname', 'cablewatch-devel0',
        'cablewatch-devel',
    ] 
    cmd += sys.argv[1:]
    print(f'* {" ".join(cmd)}')
    os.execvp(cmd[0], cmd)
    raise AssertionError('execvp() failed')


if __name__ == '__main__':
    main()
