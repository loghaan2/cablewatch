#!/usr/bin/env python3

import sys
import os


def main():
    import _bootstrap_package
    from cablewatch import config
    conf = config.Config()
    cmd = [
        'docker', 'build',
        '--build-arg', f'UID={os.getuid()}',
        '--build-arg', f'GID={os.getgid()}',
        '--build-arg', f'USER={os.getenv("USER")}',
        '--build-arg', f'PROJECT_DIR={conf.PROJECT_DIR}',
        '-f', f'{conf.PROJECT_DIR}/docker/devel.Dockerfile',
        '-t' 'cablewatch-devel',
        f'{conf.PROJECT_DIR}/docker/',
    ]
    cmd += sys.argv[1:]
    print(f'* {" ".join(cmd)}')
    os.execvp(cmd[0], cmd)
    raise AssertionError('execvp() failed')


if __name__ == '__main__':
    main()
