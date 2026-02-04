import os
import sys
import sphinx_gizeh


project = 'cablewatch docs'
author = 'loghaan'
release = '0.1'
extensions = [
    'sphinx.ext.mathjax',
    'myst_parser',
    'sphinx_gizeh'
]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
root_doc = sphinx_gizeh.get_define_from_cmdline('root_doc')
html_static_path = ['_static']
rst_epilog = """
.. |br| raw:: html

    <br/>


.. |pgbr| raw:: html

    <p class="page-break">page-break</p>


.. |nbsp| raw:: html

    &nbsp;
"""


if root_doc == 'report':
    gizeh_weasyprint = True
    gizeh_docnames = [root_doc]
    extensions.append('sphinx.ext.autosectionlabel')
    numfig = True
    html_theme = 'gizeh-repit'
    html_secnumber_suffix = ". "
    autosectionlabel_prefix_document = True
    gizeh_sass_filenames = ['_sass/report.sass']


elif root_doc == 'slides':
    gizeh_weasyprint = True
    gizeh_docnames = [root_doc]
    html_theme = 'gizeh-aton'
    gizeh_sass_filenames = ['_sass/slides.sass']


elif root_doc == 'rtd':
    html_theme = 'sphinx_rtd_theme'
    gizeh_docnames = [root_doc, 'README', 'ROADMAP']


elif root_doc == 'project_proposal':
    gizeh_docnames = [root_doc]
    extensions.append('sphinx_revealjs')
    revealjs_style_theme = 'night'
    revealjs_script_conf = {}
    revealjs_static_path = ['_static']
