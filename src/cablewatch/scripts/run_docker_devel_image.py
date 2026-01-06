#!/usr/bin/env python3

import sys
import os
import pathlib


def main():
    import _bootstrap_package
    from cablewatch import config
    conf = config.Config()
    cmd = [
        'docker', 'run',
        '-v', '/home:/home',
        '-v', f'{conf.PROJECT_DIR}/.cache/docker-volumes/pyenv-versions:/customization/pyenv/versions',
        '--user', f'{os.getuid()}:{os.getgid()}',
        '-it', '--rm',
        '--hostname', 'cablewatch-devel0',
        '-e', f'TZ={conf.TIMEZONE}',
        'cablewatch-devel',
    ] 
    cmd += sys.argv[1:]
    print(f'* {" ".join(cmd)}')
    os.execvp(cmd[0], cmd)
    raise AssertionError('execvp() failed')


if __name__ == '__main__':
    main()
