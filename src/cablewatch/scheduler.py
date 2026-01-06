from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from cablewatch import config


class SchedulerService:
    def __init__(self, ingest_service):
        self._ingest_service = ingest_service
        self._sched = None

    async def start(self):
        conf = config.Config()
        sched = AsyncIOScheduler(timezone=conf.TIMEZONE)
        logger.info("scheduler service starting")
        sched.add_job(self.record, trigger="cron", hour=6, minute=25)
        sched.add_job(self.halt, trigger="cron", hour=0, minute=5)
        sched.start()
        self._sched = sched
        logger.info("scheduler service started")

    async def stop(self):
        logger.info("scheduler service stoping")
        sched = self._sched
        if sched is not None:
            sched.shutdown()
        logger.info("scheduler service stopped")

    def record(self):
        logger.warning("record requested by scheduler")
        self._ingest_service.requestRecording()

    def halt(self):
        logger.warning("halt requested by scheduler")
        self._ingest_service.requestHalt()
