================
 ``cablewatch``
================
----------------
 ``README.rst``
----------------


Requirements
=========================

.. code-block:: shell-session

    $ sudo apt-get install ffmpeg yt-dlp tesseract-ocr tesseract-ocr-fra



Setup virtual environment
=========================

.. code-block:: shell-session

    $ pyenv install 3.13.9
    $ pyenv virtualenv 3.13.9 cablewatch
    $ pyenv activate cablewatch
    (cablewatch) $ pip install [-e] .


Build the docs
==============

.. code-block:: shell-session

    (cablewatch) $ make docs


Documentation files are then available at the following locations:
    - ``docs/build/README/README/index.html`` (this README document)
    - ``docs/build/project_proposal/project_proposal/index.html`` (project proposal slides)


Ingest service
==============

Launch the service
~~~~~~~~~~~~~~~~~~

.. code-block:: shell-session

    (cablewatch) $ cablewatch-ingest
    10:06:55 INFO cablewatch.http starting web service
    10:06:55 INFO cablewatch.http web service started
    10:06:55 INFO cablewatch.ingest starting ingest service
    10:06:55 INFO cablewatch.ingest ingest service started
    10:06:55 INFO cablewatch.ingest run recording
    10:06:55 INFO cablewatch.ingest command is 'yt-dlp -f best -o - https://...
    (...)


Video segments files are written in ``data/ingest/``. Logs are available in ``logs/``
stored in files followin the ``ingest_YYYY-MM-DD_HHhmm.log``.


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

    (cablewatch) $ wscat -c ws://127.0.0.1:8000/api/ingest
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
