#!/usr/bin/env python3

import sys
import os
import socket


def is_port_free(port, host="0.0.0.0"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def main():
    import _bootstrap_package # noqa: F401
    from cablewatch import config
    conf = config.Config()
    cmd = [
        'docker', 'run',
        '-v', '/home:/home',
        '-v', f'{conf.PROJECT_DIR}/.cache/docker-volumes/pyenv-versions:/customization/pyenv/versions',
        '--user', f'{os.getuid()}:{os.getgid()}',
    ]
    if is_port_free(conf.WEB_PORT):
        cmd += ['-p', f'0.0.0.0:{conf.WEB_PORT}:{conf.WEB_PORT}']
    cmd += [
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
