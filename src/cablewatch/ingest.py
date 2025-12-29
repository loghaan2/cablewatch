import os
import signal
import asyncio
import re
import textwrap
import time
from datetime import datetime, timedelta
from loguru import logger
from aiohttp import web,  WSCloseCode
import psutil
from cablewatch import config
from cablewatch.decorators import http_get


SEGMENT_DURATION = 30
SEGMENT_FORMAT = 'segment_%Y-%m-%d_%Hh%M-%Ss.ts'


class IngestService:
    COMMAND = f"""
        yt-dlp -f best
          {{yt_dlp_extra_args}}
          -o - {{url}}
        |
          ffmpeg -re
          -i pipe:0
          -y
          -c copy
          -f hls
          -hls_time {SEGMENT_DURATION}
          -hls_flags program_date_time
          -hls_list_size 1
          -strftime 1
          -hls_segment_filename tmp/segment_%s.ts
          tmp/output.m3u8
    """

    HLS_EXT_INF = '#EXTINF:'
    HLS_EXT_PROGDT = '#EXT-X-PROGRAM-DATE-TIME:'

    def __init__(self, *, http_service, recording_requested=True):
        conf = config.Config()
        self._recording_requested = recording_requested
        cmd = self.COMMAND
        cmd = textwrap.dedent(cmd)
        cmd = cmd.format(url=conf.INGEST_YOUTUBE_STREAM_URL, yt_dlp_extra_args=conf.YT_DLP_EXTRA_ARGS)
        cmd = cmd.replace('\n', ' ')
        cmd = cmd.strip()
        self._command = cmd
        self._proc = None
        self._background_task = None
        self._status_websockets = set()
        self._service_start_time = None
        self._record_start_time = None
        self._halt_start_time = None
        self._background_task = None
        self._current_cmd_log_level = None
        self._number_of_launched_records = 0
        self._number_of_failed_records = 0
        self._drifts = []
        http_service.addDecoratedRoutes(self)

    async def start(self):
        logger.info("starting ingest service")
        self._service_start_time = datetime.today()
        task = asyncio.create_task(self.runBackgroundTask())
        task.add_done_callback(self.runBackgroundTaskDone)
        self._background_task = task
        logger.info("ingest service started")

    async def runBackgroundTask(self):
        while True:
            if self._recording_requested:
                await self.runCommand()
            else:
                await self.halt()

    async def halt(self):
        self._halt_start_time = datetime.today()
        await self.pushStatus()
        while True:
            for i in range(100):
                if self._recording_requested:
                    return
                await asyncio.sleep(0.3)
                if i==99:
                    logger.info('halt')

    def getDriftAverage(self):
        sum = timedelta(seconds=0)
        for drift in self._drifts:
            sum += drift
        return sum / len(self._drifts)

    async def processLineIssuedByCommand(self, line):
        if line.startswith('frame='):
            return
        m = re.search(r'^\[https @ 0x[0-9a-f]+\] Opening', line)
        if m:
            return
        m = re.search(r"\[hls @ 0x[0-9a-f]+\] Skip \('(\S+)'\)", line)
        if m:
            if m.group(1).startswith(self.HLS_EXT_PROGDT):
                dt = datetime.fromisoformat(m.group(1)[len(self.HLS_EXT_PROGDT):])
                dt = dt.astimezone()
                drift = datetime.now().astimezone() - dt
                self._drifts += [drift]
                self._drifts = self._drifts[-4:]
                logger.info(f'drift: {self.getDriftAverage().total_seconds():0.1f}s')
            return
        m = re.search(r"^\[hls @ 0x[0-9a-f]+\] Opening '(\S+)' for writing", line)
        if m:
            fn = m.group(1)
            if fn.endswith('.ts'):
                self._tmp_segment_filename = fn
            elif fn.endswith('.m3u8.tmp'):
                self.processM3U8Output(fn)
            return 'INFO'
        return self._current_cmd_log_level

    def processM3U8Output(self, fn):
        with open(fn[:-4],'r') as f:
            count = 0
            duration = None
            while True:
                ln = f.readline()
                if len(ln) == 0:
                    break
                if ln.endswith('\n'):
                    ln=ln[:-1]
                if ln.startswith(self.HLS_EXT_INF):
                    L = len(self.HLS_EXT_INF)
                    duration = float(ln[L:-1])
                    count += 1
                if ln.startswith(self.HLS_EXT_PROGDT):
                    L = len(self.HLS_EXT_PROGDT)
                    dt = datetime.strptime(ln[L:], "%Y-%m-%dT%H:%M:%S.%f%z")
                    dt = dt - self.getDriftAverage()
                    self._segment_filename = dt.strftime(SEGMENT_FORMAT)
                    count += 1
                if ln.startswith('segment_'):
                    logger.info(f'move {self._tmp_segment_filename!r} to {self._segment_filename!r}')
                    os.rename(self._tmp_segment_filename, self._segment_filename)
                    self._discontinuity_marker = self._segment_filename + '.discontinuity'
                    if duration != SEGMENT_DURATION:
                        logger.warning(f'{self._segment_filename!r} duration is {duration}s')
                    count += 1
            if count < 3:
                raise AssertionError

    def removeOldTempSegments(self):
        conf = config.Config()
        now = time.time()
        dir = f'{conf.INGEST_DATADIR}/tmp'
        for fn in os.listdir(dir):
            pth = f'{dir}/{fn}'
            if os.path.isfile(pth):
                if fn.startswith('segment_'):
                    age = now - os.path.getmtime(pth)
                    if age >= 10 * 60: # 10 minutes
                        logger.info(f"remove old temp segment 'tmp/{fn}'")
                        os.remove(pth)

    async def readLineIssuedByCommand(self, stream):
        line = b''
        while True:
            ch = await stream.read(1)
            if not ch:
                return ''
            if ch==b'\r' or ch==b'\n':
                return line.strip().decode()
            else:
                line += ch

    async def runCommand(self):
        logger.info("run recording")
        logger.info(f"command is {self._command!r}")
        self._record_start_time = datetime.today()
        self._number_of_launched_records += 1
        self._tmp_segment_filename = None
        self._segment_filename = None
        self._current_cmd_log_level = 'INFO'
        try:
            conf = config.Config()
            os.chdir(f"{conf.INGEST_DATADIR}")
            proc = await asyncio.create_subprocess_shell(self._command,
                stdin = asyncio.subprocess.PIPE,
                stdout = asyncio.subprocess.PIPE,
                stderr = asyncio.subprocess.STDOUT,
            )
            logger.info(f"ingest command pid is {proc.pid}")
            self._proc = proc
            await self.pushStatus()
            i = 0
            while True:
                line = await self.readLineIssuedByCommand(proc.stdout)
                if not line:
                    break
                log_level = await self.processLineIssuedByCommand(line)
                if log_level is not None:
                    logger.bind(name=f'[from-cmd]').log(log_level, line)
                if i > 100:
                    self.removeOldTempSegments()
                    i = 0
                i += 1
            returncode = await proc.wait()
            logger.log(self._current_cmd_log_level, f'command exits with returncode {returncode}')
        finally:
            self._proc = None
            self._number_of_failed_records += 1
            await self.pushStatus()

    async def haltCommand(self):
        if self._proc is None:
            return
        parent = psutil.Process(self._proc.pid)
        children = parent.children(recursive=True)
        for pid in [self._proc.pid] + [child.pid for child in children]:
            os.kill(pid, signal.SIGTERM)
        self._proc = None
        await self.pushStatus()

    def runBackgroundTaskDone(self, future):
        if future.cancelled():
            return
        future.result()
        raise AssertionError("run() done without error")

    async def stop(self):
        message = "stopping ingest service"
        logger.info(message)
        for ws in list(self._status_websockets):
            await ws.close(code=WSCloseCode.GOING_AWAY, message=message)
        await self.haltCommand()
        if self._background_task is not None:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        logger.info("ingest service stopped")

    @http_get("/api/ingest")
    async def handleWebSocket(self, request: web.Request) -> web.WebSocketResponse():
        ws = web.WebSocketResponse()
        self._status_websockets.add(ws)
        await ws.prepare(request)
        try:
            d = self.prepareStatus()
            await ws.send_json(d)
            async for msg in ws:
                if msg.type == web.WSMsgType.CLOSE:
                    break
                elif msg.type == web.WSMsgType.TEXT:
                    if msg.data == 'record':
                        if not self._recording_requested:
                            self._recording_requested = True
                            await self.pushStatus()
                            returned_msg = "ok"
                        else:
                            returned_msg = "state error: curently recording"
                    elif msg.data == 'halt':
                        if self._recording_requested:
                            self._number_of_failed_records -= 1
                            self._recording_requested = False
                            await self.pushStatus()
                            self._current_cmd_log_level = 'INFO'
                            await self.haltCommand()
                            returned_msg = "ok"
                        else:
                            returned_msg = "state error: curently not recording"
                    else:
                        returned_msg = f"invalid command: '{msg.data}'"
                    await ws.send_json({'type': 'command-reply', 'message': returned_msg})
        finally:
            self._status_websockets.remove(ws)
        return ws

    def prepareStatus(self):
        sts = {}
        sts['type'] = 'status'
        sts['recording_requested'] = self._recording_requested
        if self._proc is not None:
            sts['pid'] = self._proc.pid
        else:
            sts['pid'] = None
        for k in 'service_start_time', 'record_start_time', 'halt_start_time':
            value = getattr(self, f'_{k}')
            if value is None:
                sts[k] = None
            else:
                sts[k] = value.strftime("%Y-%m-%d %Hh%M")
        sts['number_of_launched_records'] = self._number_of_launched_records
        sts['number_of_failed_records'] = self._number_of_failed_records
        return sts

    async def pushStatus(self):
        sts = self.prepareStatus()
        for ws in self._status_websockets:
            await ws.send_json(sts)
