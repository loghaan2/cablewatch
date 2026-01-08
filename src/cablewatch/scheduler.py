from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from cablewatch import config, speech


class SchedulerService:
    def __init__(self, ingest_service):
        self._ingest_service = ingest_service
        self._sched = None

    async def start(self):
        conf = config.Config()
        sched = AsyncIOScheduler(timezone=conf.TIMEZONE)
        logger.info("scheduler service starting")
        # sched.add_job(self.ingest_record, trigger="cron", hour=6, minute=25)
        # sched.add_job(self.ingest_halt, trigger="cron", hour=0, minute=5)
        # sched.add_job(self.speech_upload, trigger="cron", minute='*/2')
        sched.start()
        self._sched = sched
        logger.info("scheduler service started")

    async def stop(self):
        logger.info("scheduler service stoping")
        sched = self._sched
        if sched is not None:
            sched.shutdown()
        logger.info("scheduler service stopped")

    def ingest_record(self):
        logger.warning("ingest record requested by scheduler")
        self._ingest_service.requestRecording()

    def ingest_halt(self):
        logger.warning("ingest halt requested by scheduler")
        self._ingest_service.requestHalt()

    def speech_upload(self):
        logger.warning("speech upload requested by scheduler")
        se = speech.SpeechExtractor(keep=True)
        se.upload()
