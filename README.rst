================
 ``cablewatch``
================
----------------
 ``README.rst``
----------------


Setup virtual environment
=========================

.. code-block:: shell-session

    $ pyenv install 3.13.9
    $ pyenv virtualenv 3.13.9 cablewatch
    $ pyenv activate cablewatch
    $ pip install -r requirements.txt


Build the docs
==============

.. code-block:: shell-session

    $ pipenv activate cablewatch
    $ make docs


Documentation files are then available at the following locations:
    - ``docs/build/README/README/index.html`` (this README document)
    - ``docs/build/project_proposal/project_proposal/index.html`` (project proposal slides)
