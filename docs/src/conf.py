import os

SPHINX_BUILD = os.environ.get('SPHINX_BUILD')

extensions = [ ]

master_doc = f'{SPHINX_BUILD}/index'

if SPHINX_BUILD == 'project_proposal':
    extensions.append('sphinx_revealjs')
    revealjs_style_theme = 'night'
    revealjs_script_conf = {}
    revealjs_static_path = ['_static']
else:
    html_theme = 'sphinx_rtd_theme'
    html_static_path = ['_static']
