================
 ``cablewatch``
================
----------------
 ``README.rst``
----------------


Setup local virtual environment
===============================

.. code-block:: shell-session

    $ pyenv install 3.13.9
    $ pyenv virtualenv 3.13.9 cablewatch
    $ pyenv activate cablewatch
    (cablewatch) $ pip install -e .


Setup development docker image
==============================

Build
~~~~~

.. code-block:: shell-session

    $ python3 src/cablewatch/scripts/build_docker_devel_image.py
    * docker build --build-arg UID=1000 --build-arg GID=1000 --build-arg USER=...
    [+] Building 0.2s (13/13) FINISHED
    => [internal] load build definition
    (...)
    => => naming to docker.io/library/cablewatch-devel
    $


Activate
~~~~~~~~

.. code-block:: shell-session

    $ python3 src/cablewatch/scripts/run_docker_devel_image.py
    * docker run -v /home:/home -v .../cablewatch/.cache/docker-volumes/pyenv-versions:/customization/pyenv/versions --user 1000:1000 -it --rm --hostname cablewatch-devel0 cablewatch-devel
    Creating virtualenv 'cablewatch'...
    Looking in links: /tmp/tmpmuv3q3u0
    Requirement already satisfied: pip in /customization/pyenv/versions/cablewatch/lib/python3.13/site-packages (25.3)
    (cablewatch) $


Setup virtual environment
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: shell-session

    (cablewatch) $ pip install -e .


Running the tests
=================

.. code-block::

    (cablewatch) $ pytest -v tests/
    $ pytest -v tests
    Test session starts (platform: linux, Python 3.13.2, pytest 9.0.2, pytest-sugar 1.1.1)
    cachedir: .pytest_cache
    rootdir: /home/loghaan/side-projects/cablewatch
    configfile: pyproject.toml
    plugins: sugar-1.1.1
    collected 25 items

    tests/test_codequality.py::test_ruff[src/...]                    4% ▌
    tests/test_codequality.py::test_ruff[src/...]                    8% ▊
    tests/test_codequality.py::test_ruff[src/...]                   12% █▎
    tests/test_codequality.py::test_ruff[src/...]                   16% █▋
    tests/test_codequality.py::test_ruff[src/...]                   20% ██
    tests/test_codequality.py::test_ruff[src/...]                   24% ██▌
    tests/test_codequality.py::test_ruff[src/...]                   28% ██▊
    tests/test_codequality.py::test_ruff[src/...]                   32% ███▎
    tests/test_codequality.py::test_ruff[src/...]                   36% ███▋
    tests/test_codequality.py::test_ruff[src/...]                   40% ████
    tests/test_codequality.py::test_ruff[src/...]                   44% ████▌
    tests/test_codequality.py::test_ruff[src/...]                   48% ████▊
    tests/test_codequality.py::test_ruff[tests/...] ✓               52% █████▎
    tests/test_codequality.py::test_ruff[tests/...] ✓               56% █████▋
    tests/test_codequality.py::test_ruff[src/...] ✓                 60% ██████
    tests/test_codequality.py::test_ruff[src/...] ✓                 64% ██████▌
    tests/test_codequality.py::test_ruff[tests/...] ✓               68% ██████▊
    tests/test_codequality.py::test_ruff[src/...] ✓                 72% ███████
    tests/test_codequality.py::test_ruff[src/...] ✓                 76% ███████▋
    tests/test_codequality.py::test_ruff[src/...] ✓                 80% ████████
    tests/test_gcp.py::test_bucketSpeech...Folders ✓                84% ████████▌
    tests/test_gcp.py::test_bucketSpeech...launched] ✓              88% ████████▊
    tests/test_gcp.py::test_bucketSpeech...[results] ✓              92% █████████▎
    tests/test_gcp.py::test_bucketSpeech...[uploaded] ✓             96% █████████▋
    tests/test_sanity.py::test_checkFFMEGVersion ✓                 100% ██████████

    Results (2.29s):
        25 passed


Super Services
==============

All ``cablewatch`` services (ingest, web, orchestration, ...) are running in a single process.


Web users managment
~~~~~~~~~~~~~~~~~~~

To use the web service, a user must be created:

.. code-block:: shell-session

    (cablewatch) $ cablewatch-adduser
    Username: loghaan
    Password: <you_will_never_guess_this_ha_ha_ha>
    Roles: admin

    Just copy the content below to your cablewatch-local.toml:

    [[users]]
    username = "loghaan"
    password_hash = "5c0e24af..."
    roles = "admin"

Just copy the ``[[users]]`` section in ``cablewatch-local.toml`` to finalize the user creation. For now there is only the
``admin`` role which has some extra pivileges.


Launch the services
~~~~~~~~~~~~~~~~~~~

.. code-block:: shell-session

    (cablewatch) $ cablewatch-super
    10:06:55 INFO cablewatch.http starting web service
    10:06:55 INFO cablewatch.http web service started
    10:06:55 INFO cablewatch.ingest starting ingest service
    10:06:55 INFO cablewatch.ingest ingest service started
    10:06:55 INFO cablewatch.ingest run recording
    10:06:55 INFO cablewatch.ingest command is 'yt-dlp -f best -o - https://...
    (...)

This start all the services.


Ingest
~~~~~~

Video segments files are written in ``data/ingest/``. Logs are available in ``logs/``
stored in files followin the ``YYYYMMDD_HHhmm.log``.


Control/monitor the service via its *backoffice* web page
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Web service is running on port ``8000``. Open ``http://127.0.0.1:8000/ingest.html`` with your browser.


Control/monitor the service via its web ``API``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Web service is running on port ``8000``. Open ``http://127.0.0.1:8000/ingest.html`` with your browser.

You need a websocket client tool to "speak" with the ``API``. ``wscat`` can do the job but other tools
exists. ``wscat`` can be installed with the following commands:


.. code-block:: shell-session

    $ npm install wscat


.. code-block:: shell-session

    (cablewatch) $ wscat -c ws://127.0.0.1:8000/api/ingest --auth loghaan:you_will_never_guess_this_ha_ha_ha>
    Connected (press CTRL+C to quit)
    < {"type": "status", "recording_requested": true, "pid": 28621, "service_start_time": ...

    > halt
    < {"type": "status", "recording_requested": false, "pid": 28621, "service_start_time": ...
    < {"type": "status", "recording_requested": false, "pid": null, "service_start_time": ...
    < {"type": "command-reply", "message": "ok"}
    < {"type": "status", "recording_requested": false, "pid": null, "service_start_time": ...
    < {"type": "status", "recording_requested": false, "pid": null, "service_start_time": ...

    > record
    < {"type": "status", "recording_requested": true, "pid": null, "service_start_time": ...
    < {"type": "command-reply", "message": "ok"}
    < {"type": "status", "recording_requested": true, "pid": 29545, "service_start_time": ...
    < {"type": "status", "recording_requested": true, "pid": 29545, "service_start_time": ...
    > 


Build the docs
==============

.. code-block:: shell-session

    (cablewatch) $ make docs


Documentation files are then available at the following locations:
    - ``docs/build/README/README/index.html`` (this README document)
    - ``docs/build/ROADMAP/ROADMAP/index.html`` (from ``ROADMAP.md``)
    - ``docs/build/project_proposal/project_proposal/index.html`` (project proposal slides)
