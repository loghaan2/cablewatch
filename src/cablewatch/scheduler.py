from datetime import datetime, time
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from cablewatch import config, speech, banners
from cablewatch.decorators import log_exception


class SchedulerService:
    WAKUP_INTERVAL = 60
    INGEST_DORECORD_TIME = time(hour=6, minute=25)
    INGEST_DOHALT_TIME = time(hour=0, minute=5)
    TIMELINE_DURATION = 900

    def __init__(self, *,
            ingest_service,
            ingest_planification=True,
            speech_init=True,
            speech_planification=True,
            banners_init=True,
            banners_planification=True,
            timeline_duration=None,
        ):
        self._ingest_service = ingest_service
        self._ingest_planification = ingest_planification
        self._speech_init = speech_init
        self._speech_planification = speech_planification
        self._banners_init = banners_init
        self._banners_planification = banners_planification
        if timeline_duration is None:
            self._timeline_duration = self.TIMELINE_DURATION
        else:
            self._timeline_duration = timeline_duration.total_seconds()
        logger.info(f"timeline duration is {self._timeline_duration}s")
        self._sched = None
        ingest_service.registerScheduler(self)

    async def start(self):
        logger.info("scheduler service starting")
        conf = config.Config()
        executors = {
            'default': ThreadPoolExecutor(max_workers=1),
            'speech': ThreadPoolExecutor(max_workers=1),
            'speech-gcp': ThreadPoolExecutor(max_workers=1),
            'banners': ThreadPoolExecutor(max_workers=1),
        }
        sched = BackgroundScheduler(timezone=conf.TIMEZONE, executors=executors)
        self._sched = sched
        # ingest on first segment
        sched.add_job(self.ingest_onfirstseg, trigger="interval", days=1000, id="ingest-onfirstseg") # triggered from ingest service
        # ingest planification job
        if self._ingest_planification:
            logger.warning('ingest record/halt daily planification jobs:')
            sched.add_job(self.ingest_dorecord, trigger="cron", hour=self.INGEST_DORECORD_TIME.hour, minute=self.INGEST_DORECORD_TIME.minute)
            logger.warning(f'  - record at {self.INGEST_DORECORD_TIME}')
            sched.add_job(self.ingest_dohalt, trigger="cron", hour=self.INGEST_DOHALT_TIME.hour, minute=self.INGEST_DOHALT_TIME.minute)
            logger.warning(f'  - halt at {self.INGEST_DOHALT_TIME}')
        else:
            logger.warning('no ingest planification')
        # speech planification job
        if self._speech_planification:
            sched.add_job(self.speech_upload, trigger="interval", seconds=self.WAKUP_INTERVAL, executor="speech")
            sched.add_job(self.speech_launch, trigger="interval", seconds=self.WAKUP_INTERVAL, executor="speech-gcp")
            sched.add_job(self.speech_fetch, trigger="interval", seconds=self.WAKUP_INTERVAL, executor="speech-gcp")
            logger.warning('register speech planification jobs')
        else:
            logger.warning('no speech planification')
        # banners planification job
        if self._banners_planification:
            sched.add_job(self.banners_extract, trigger="interval", seconds=self.WAKUP_INTERVAL, executor="banners")
            logger.warning('register banners planification jobs')
        else:
            logger.warning('no banners planification')
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
    def ingest_onfirstseg(self):
        logger.warning("ingest_onfirstseg()")
        begin = self._ingest_service.getCurrentSegmentTimestamp()
        begin = begin.strftime("%Y%m%d_%Hh%Mm%S")
        duration = f'{self._timeline_duration}s'
        if self._speech_init:
            tool = speech.SpeechTool(action='init', begin=begin, duration=duration)
            tool()
        if self._banners_init:
            tool = banners.BannersTool(action='init', begin=begin, duration=duration)
            tool()
        logger.warning("/ingest_onfirstseg()")

    @log_exception
    def speech_upload(self):
        logger.warning("speech_upload()")
        tool = speech.SpeechTool(action='upload')
        tool()
        logger.warning("/speech_upload()")

    @log_exception
    def speech_launch(self):
        logger.warning("speech_launch()")
        tool = speech.SpeechTool(action='launch')
        tool()
        logger.warning("/speech_launch()")

    @log_exception
    def speech_fetch(self):
        logger.warning("speech_fetch()")
        tool = speech.SpeechTool(action='fetch')
        tool()
        logger.warning("/speech_fetch()")

    @log_exception
    def banners_extract(self):
        logger.warning("banners_extract()")
        tool = banners.BannersTool(action='extract')
        tool()
        logger.warning("/banners_extract()")
