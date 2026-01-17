import asyncio
import signal
import argparse
import sys
import os
from loguru import logger
from cablewatch import http, loghlp, ingest, scheduler


def make_synchrone(async_func):
    def inner():
        return asyncio.run(async_func())
    return inner



class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super().__init__()
        self.add_argument('-n', '--no-record-planification', dest='record_planification', default=True, action='store_false', help="no record planification")

    def parse_args(self, args):
        ns = super().parse_args(args[1:])
        ns.prog = os.path.basename(args[0])
        return ns


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
    loghlp.setup(fileoutput=True)
    p = ArgumentParser()
    logger.info(f'args: {sys.argv[1:]}')
    ns = p.parse_args(sys.argv)
    logger.info(f'ns: {ns}')
    aborter = Aborter()
    http_service = http.HTTPService()
    ingest_service = ingest.IngestService(http_service=http_service, aborter=aborter)
    scheduler_service = scheduler.SchedulerService(ingest_service=ingest_service, record_planification=ns.record_planification)
    await http_service.start()
    await scheduler_service.start()
    await ingest_service.start()
    await aborter.wait()
    await ingest_service.stop()
    await scheduler_service.stop()
    await http_service.stop()
    logger.complete()
