import asyncio
import signal
import sys
from loguru import logger
from cablewatch import http, ingest, scheduler, arghlp, papers


def make_synchrone(async_func):
    def inner():
        return asyncio.run(async_func())
    return inner


class Aborter:
    def __init__(self):
        ev = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.onSignal)
        self._interrupt_event = ev

    def wakeup(self):
        loop = asyncio.get_running_loop()
        ev = self._interrupt_event
        ev.set()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)

    def onSignal(self):
        logger.warning("aborted by user (UNIX signal)")
        self.wakeup()

    def abort(self):
        logger.error("aborted from code")
        self.wakeup()

    async def wait(self):
        ev = self._interrupt_event
        await ev.wait()


@make_synchrone
async def main():
    p = arghlp.ArgumentParser(classname="SuperService")
    logger.info(f'args: {sys.argv[1:]}')
    ns = p.parse_args(sys.argv)
    logger.info(f'ns: {ns}')
    aborter = Aborter()
    http_service = http.HTTPService()
    ingest_service = ingest.IngestService(
        http_service=http_service,
        aborter=aborter,
        recording_requested=ns.ingest_record,
    )
    scheduler_service = scheduler.SchedulerService(
        ingest_service=ingest_service,
        ingest_planification=ns.ingest_planification,
        speech_init=ns.speech_init,
        speech_planification=ns.speech_planification,
        banners_init=ns.banners_init,
        banners_planification=ns.banners_planification,
        timeline_duration=ns.duration,
    )
    papers_service = papers.PapersService(
        http_service=http_service,
    )
    await http_service.start()
    await scheduler_service.start()
    await ingest_service.start()
    await papers_service.start()
    await aborter.wait()
    await papers_service.stop()
    await ingest_service.stop()
    await scheduler_service.stop()
    await http_service.stop()
    logger.complete()
