#!/usr/bin/env python3

import subprocess
import os

THEMES = 'report', 'slides'

MASTER_DOCS = {
    'report': 'html+weasyprint',
    'slides': 'html+weasyprint',
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
    for thm in THEMES:
        system(f"sassc _themes/{thm}/sass/style.sass _themes/{thm}/static/style.css")
    for master_doc, backend in MASTER_DOCS.items():
        if 'html' in backend:
            system(f"CABLEWATCH_MASTER_DOC={master_doc} sphinx-build -E -b html . ../build/{master_doc}")
        if 'weasyprint' in backend:
            system(f"weasyprint ../build/{master_doc}/{master_doc}.html ../build/{master_doc}/{master_doc}.pdf")


if __name__ == '__main__':
    main()
