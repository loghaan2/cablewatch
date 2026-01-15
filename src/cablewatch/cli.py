import asyncio
import signal
import sys
import requests
from loguru import logger
from bs4 import BeautifulSoup
from cablewatch import config, http, loghlp, ingest, scheduler


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
async def main_services():
    loghlp.setup(fileoutput=True)
    aborter = Aborter()
    http_service = http.HTTPService()
    ingest_service = ingest.IngestService(http_service=http_service, aborter=aborter)
    scheduler_service = scheduler.SchedulerService(ingest_service=ingest_service)
    await http_service.start()
    await ingest_service.start()
    await scheduler_service.start()
    await aborter.wait()
    await scheduler_service.stop()
    await ingest_service.stop()
    await http_service.stop()
    logger.complete()


def main_download_roadmap():
    conf = config.Config()
    response = requests.get(f'{conf.ROADMAP_HACKMD_URL}')
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    div = soup.find("div", id="publish-page")
    if not div:
        raise AssertionError("Cannot find publish page")
    with open("ROADMAP.md", 'w') as f:
        f.write(div.get_text(strip=True))


def main_timeline():
    tool = ingest.IngestTimeLineTool(sys.argv)
    tool()
