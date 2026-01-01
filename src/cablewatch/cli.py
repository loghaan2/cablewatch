import asyncio
import signal
import requests
from loguru import logger
from bs4 import BeautifulSoup
from cablewatch import config, http, loghlp, ingest


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

    def onSignal(self):
        logger.warning("aborted by user (UNIX signal)")
        ev = self._interrupt_event
        ev.set()

    def abort(self):
        logger.error("aborted from code")
        ev = self._interrupt_event
        ev.set()

    async def wait(self):
        ev = self._interrupt_event
        await ev.wait()


@make_synchrone
async def main_ingest():
    loghlp.setup()
    aborter = Aborter()
    http_service = http.HTTPService()
    ingest_service = ingest.IngestService(http_service=http_service, aborter=aborter)
    await http_service.start()
    await ingest_service.start()
    await aborter.wait()
    await ingest_service.stop()
    await http_service.stop()


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
