import asyncio
import signal
from loguru import logger
from cablewatch import config, http, loghlp, ingest


def make_synchrone(async_func):
    def inner():
        return asyncio.run(async_func())
    return inner


class UNIXSignalsManager:
    def __init__(self):
        ev = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, ev.set)
        self._interrupt_event = ev

    async def waitInterruptSignal(self):
        await self._interrupt_event.wait()
        logger.warning("interrupt signal detected")


@make_synchrone
async def ingest_main():
    loghlp.setup()
    mng = UNIXSignalsManager()
    http_service = http.HTTPService()
    ingest_service = ingest.IngestService(http_service=http_service)
    await http_service.start()
    await ingest_service.start()
    await mng.waitInterruptSignal()
    await ingest_service.stop()
    await http_service.stop()
