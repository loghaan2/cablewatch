#!/usr/bin/env python3

import subprocess
import os
import sys

THEMES = 'report', 'slides'

ROOT_DOCS_OPTIONS = {
    'report': 'html',
    'slides': 'html',
    'rtd': 'html',
    'project_proposal': 'revealjs',
}


def system(cmd):
    print(f'* {cmd}')
    subprocess.run(cmd, shell=True, check=True)


def main():
    try:
        import _bootstrap_package # noqa: F401
    except ImportError:
        pass
    from cablewatch import config
    conf = config.Config()
    os.chdir(f'{conf.PROJECT_DIR}/docs/src')
    root_docs = sys.argv[1:]
    if len(root_docs) == 0:
        root_docs = ROOT_DOCS_OPTIONS.keys()
    for root_doc in root_docs:
        backend = ROOT_DOCS_OPTIONS[root_doc]
        system(f"sphinx-build -Droot_doc={root_doc} -E -b {backend} . ../build/{root_doc}")


if __name__ == '__main__':
    main()
