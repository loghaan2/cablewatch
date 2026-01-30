import os
import sys
sys.path.insert(0, os.path.abspath('.'))


project = 'cablewatch docs'
author = 'loghaan'
release = '0.1'

master_doc = os.getenv('CABLEWATCH_MASTER_DOC', 'report')


extensions = [
    'sphinx.ext.mathjax',
    'myst_parser',
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

if master_doc == 'report':
    extensions.append('sphinx.ext.autosectionlabel')
    numfig = True
    html_theme = 'report'
    html_theme_path = ['_themes']
    html_static_path = ['_static', '_themes/report/static', '_themes/report/images']
    html_theme_options = {
        "navigation_depth": 4,
    }
    html_secnumber_suffix = ". "
    autosectionlabel_prefix_document = True

elif master_doc == 'slides':
    html_theme = 'slides'
    html_theme_path = ['_themes']
    html_static_path = ['_static', '_themes/slides/static', '_themes/slides/images']

elif master_doc == 'rtd':
    html_theme = 'sphinx_rtd_theme'
    html_static_path = ['_static']

elif master_doc == 'project_proposal':
    extensions.append('sphinx_revealjs')
    revealjs_style_theme = 'night'
    revealjs_script_conf = {}
    revealjs_static_path = ['_static']

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

plantuml_output_format = 'png'

rst_epilog = """
.. |br| raw:: html

  <br/>


.. |pgbr| raw:: html

  <p class="page-break">page-break</p>


.. |nbsp| raw:: html

    &nbsp;
"""
