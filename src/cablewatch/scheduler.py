from datetime import datetime, time
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from cablewatch import config, speech
from cablewatch.decorators import log_exception


class SchedulerService:
    SPEECH_LAUNCH_OR_FETCH_SECONDS = speech.SpeechExtractor.TIMELINE_DURATION * 4
    DO_RECORD_TIME = time(hour=6, minute=25)
    DO_HALT_TIME = time(hour=0, minute=5)

    def __init__(self, *, ingest_service, record_planification=True):
        self._ingest_service = ingest_service
        self._sched = None
        self._launch_or_fetch = 'launch'
        self._record_planification = record_planification
        ingest_service.registerScheduler(self)

    async def start(self):
        logger.info("scheduler service starting")
        conf = config.Config()
        executors = {
            'default': ThreadPoolExecutor(max_workers=1),
            'speech-upload': ThreadPoolExecutor(max_workers=1),
            'speech-launch-or-fetch': ThreadPoolExecutor(max_workers=1),
        }
        sched = BackgroundScheduler(timezone=conf.TIMEZONE, executors=executors)
        self._sched = sched
        logger.warning('ingest record/halt daily planification jobs:')
        if self._record_planification:
            sched.add_job(self.ingest_dorecord, trigger="cron", hour=self.DO_RECORD_TIME.hour, minute=self.DO_RECORD_TIME.minute)
            logger.warning(f'  - record at {self.DO_RECORD_TIME}')
            sched.add_job(self.ingest_dohalt, trigger="cron", hour=self.DO_HALT_TIME.hour, minute=self.DO_HALT_TIME.minute)
            logger.warning(f'  - halt at {self.DO_HALT_TIME}')
        else:
            logger.warning('  (none)')
        sched.add_job(self.ingest_onrecord, trigger="interval", days=1000, id="ingest-onrecord") # triggered from ingest service
        sched.add_job(self.ingest_onhalt, trigger="interval", days=1000, id="ingest-onhalt") # triggered from ingest service
        sched.add_job(self.speech_upload, trigger="interval", seconds=speech.SpeechExtractor.TIMELINE_DURATION, executor='speech-upload')
        sched.add_job(self.speech_launch_or_fetch, trigger="interval", seconds=self.SPEECH_LAUNCH_OR_FETCH_SECONDS, executor='speech-launch-or-fetch')
        sched.start()
        logger.info("scheduler service started")

    async def stop(self):
        logger.info("scheduler service stopping")
        sched = self._sched
        if sched is not None:
            sched.shutdown()
        logger.info("scheduler service stopped")

    def triggerJob(self, job_id):
        job = self._sched.get_job(job_id)
        if job is None:
            logger.error(f"no job with id {job_id!r}")
            return
        job.modify(next_run_time=datetime.now())

    @log_exception
    def ingest_dorecord(self):
        logger.warning("ingest_dorecord()")
        self._ingest_service.requestRecording()
        logger.warning("/ingest_dorecord()")

    @log_exception
    def ingest_dohalt(self):
        logger.warning("ingest_dohalt()")
        self._ingest_service.requestHalt()
        logger.warning("/ingest_dohalt()")

    @log_exception
    def ingest_onrecord(self):
        logger.warning("ingest_onrecord()")
        se = speech.SpeechExtractor()
        se.initTimeline()
        logger.warning("/ingest_onrecord()")

    @log_exception
    def ingest_onhalt(self):
        logger.warning("ingest_onhalt()")
        logger.warning("/ingest_onhalt()")

    @log_exception
    def speech_upload(self):
        logger.warning("speech_upload()")
        se = speech.SpeechExtractor()
        se.convertAndUpload()
        logger.warning("/speech_upload()")

    @log_exception
    def speech_launch_or_fetch(self):
        logger.warning("speech_launch_or_fetch()")
        se = speech.SpeechExtractor()
        if self._launch_or_fetch == 'launch':
            se.launchTranscriptions()
            self._launch_or_fetch = 'fetch'
        else:
            se.fetchResults()
            self._launch_or_fetch = 'launch'
        logger.warning("/speech_launch_or_fetch()")
