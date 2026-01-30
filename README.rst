================
 ``README.rst``
================

.. after-titles



Setup Local Virtual Environment
===============================

.. code-block:: shell-session

    $ pyenv install 3.13.9
    $ pyenv virtualenv 3.13.9 cablewatch
    $ pyenv activate cablewatch
    (cablewatch) $ pip install -e .


Setup Development Docker Image
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


Setup Virtual Environment
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: shell-session

    (cablewatch) $ pip install -e .

|pgbr|


Local Configuration File
========================

To make the project work correctly, a local ``cablewatch-local.toml`` file must be created.  
Simply copy ``cablewatch-local.toml.sample`` to ``cablewatch-local.toml`` and edit it according
to your local needs:

.. literalinclude:: ../../cablewatch-local.toml.sample


|pgbr|


User Management
~~~~~~~~~~~~~~~

To use the web service, a user must be created:

.. code-block:: shell-session

    (cablewatch) $ cablewatch-adduser
    Username: loghaan
    Password: <you_will_never_guess_this_ha_ha_ha>
    Roles: admin

    Copy the content below into your ``cablewatch-local.toml`` file:

    [[users]]
    username = "loghaan"
    password_hash = "5c0e24af..."
    roles = "admin"

Copy the ``[[users]]`` section into ``cablewatch-local.toml`` to finalize the user creation.  
For now, only the ``admin`` role exists, which grants additional privileges.


Super Services
==============

All ``cablewatch`` services (ingest, web, orchestration, …) run within a single process.


Launching the Services
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: shell-session

    (cablewatch) $ cablewatch-super
    10:06:55 INFO cablewatch.http starting web service
    10:06:55 INFO cablewatch.http web service started
    10:06:55 INFO cablewatch.ingest starting ingest service
    10:06:55 INFO cablewatch.ingest ingest service started
    10:06:55 INFO cablewatch.ingest run recording
    10:06:55 INFO cablewatch.ingest command is 'yt-dlp -f best -o - https://...
    (...)

This command starts all services.

|pgbr|


Ingest Service
==============

Video segment files are written to ``data/ingest/``.

Control / monitor the service via the *backoffice* web page
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The web service runs on port ``8000``. Open ``http://127.0.0.1:8000/ingest.html`` in your browser.


Control / monitor the service via the web ``API``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The web service runs on port ``8000``. Open ``http://127.0.0.1:8000/ingest.html`` in your browser.

A WebSocket client tool is required to interact with the ``API``. ``wscat`` can be used for this
purpose, although other tools exist. ``wscat`` can be installed using the following command:

.. code-block:: shell-session

    $ npm install wscat


.. code-block:: shell-session

    (cablewatch) $ wscat -c ws://127.0.0.1:8000/api/ingest --auth loghaan:<you_will_never_guess_this_ha_ha_ha>
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


Papers Service
==============

Generated papers are written to ``data/papers/``.


Lookup / download papers via the *backoffice* web page
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The web service runs on port ``8000``. Open ``http://127.0.0.1:8000/papers.html`` in your browser.


Lookup / download papers via the *backoffice* web ``API``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

List papers
-----------

.. code-block:: shell-session

    (cablewatch) $ curl -u loghaan:<you_will_never_guess_this_ha_ha_ha> http://192.168.0.102:8000/api/papers/list | jq .
    % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                     Dload  Upload   Total   Spent    Left  Speed
    100  1948 100  1948   0     0 48070     0  --:--:-- --:--:-- --:--:-- 48700
    [
        "20260128_16h50__Le-16h-18h.json",
        "20260128_17h54__Vrai-ou-Faux.json",
        (...)
        "20260130_21h59__Le-Pour-et-le-Contre.json",
        "20260130_22h58__Le-23h.json"
    ]


Download first paper
--------------------

.. code-block:: shell-session

    (cablewatch) $
    curl -u loghaan:<you_will_never_guess_this_ha_ha_ha> -OJ 'http://192.168.0.102:8000/api/papers/download/0'


Download all papers as archive
------------------------------

.. code-block:: shell-session

    (cablewatch) $ curl -u loghaan:<you_will_never_guess_this_ha_ha_ha> -OJ 'http://192.168.0.102:8000/api/papers/download-archive/*matinale*'


List and filter papers
----------------------

.. code-block:: shell-session

    (cablewatch) $ curl -u loghaan:<you_will_never_guess_this_ha_ha_ha> 'http://192.168.0.102:8000/api/papers/list/*matinale*' |jq .
    % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
    100   216 100   216   0     0  5014     0  --:--:-- --:--:-- --:--:--  5023
    [
        "20260129_06h32__La-matinale.json",
        "20260129_09h00__La-matinale.json",
        "20260130_06h29__La-matinale.json",
        "20260130_06h59__La-matinale.json",
        "20260130_07h30__La-matinale.json",
        "20260130_08h58__La-matinale.json"
    ]


Download first filtered paper
-----------------------------

.. code-block:: shell-session

    (cablewatch) $ curl -u loghaan:<you_will_never_guess_this_ha_ha_ha> -OJ 'http://192.168.0.102:8000/api/papers/download/*matinale*/0'


Download all filtered papers as archive
---------------------------------------

.. code-block:: shell-session

    (cablewatch) $ curl -u loghaan:<you_will_never_guess_this_ha_ha_ha> -OJ 'http://192.168.0.102:8000/api/papers/download-archive/*matinale*'


Logs
====

Logs are available in ``logs/`` stored in files following the ``YYYYMMDD_HHhmm.log`` pattern.



Build the Documentation
=======================

.. code-block:: shell-session

    (cablewatch) $ cablewatch-build-docs


Documentation files are then available at the following locations:
    - ``docs/build/report/report.pdf``
    - ``docs/build/rtd/rtd.html`` (this includes ``README.rst`` and ``ROADMAP.md``)
    - ``docs/build/project_proposal/project_proposal.html`` (project proposal slides)





Running Tests
=============

.. code-block:: shell-session

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


Google Cloud CLI Notes
~~~~~~~~~~~~~~~~~~~~~~

Don't forget to logging to glcoud beforer using ``cablewatch-speech``:

.. code-block:: shell-session

    $ gcloud auth login                       # Authenticates the user for the CLI
    $ gcloud auth application-default login   # Authenticates applications (SDK, libs)
