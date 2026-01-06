import os
import sys
import signal
import asyncio
import re
import textwrap
import time
import glob
import json
import argparse
import tempfile
import copy
import shlex
from datetime import datetime, timedelta
from pytimeparse.timeparse import timeparse
from loguru import logger
from aiohttp import web,  WSCloseCode
import psutil
from rich import print
from rich.table import Table
from cablewatch import config
from cablewatch.decorators import http_get


SEGMENT_DURATION = 30
SEGMENT_DATETIME_FORMAT = '%Y-%m-%dT%Hh%Mm%S'
SEGMENT_FORMAT = 'segment_{datetime}_{duration:.2f}s.ts'
SEGMENT_PATTERN = r'^segment_(.+)_(.+)s\.ts(\.hole)?$'


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

    def __init__(self, *, http_service, recording_requested=True, aborter=None):
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
        self._aborter = aborter
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
                    self._segment_filename = SEGMENT_FORMAT.format(datetime=dt.strftime(SEGMENT_DATETIME_FORMAT), duration=duration)
                    count += 1
                if ln.startswith('segment_'):
                    logger.info(f'move {self._tmp_segment_filename!r} to {self._segment_filename!r}')
                    os.rename(self._tmp_segment_filename, self._segment_filename)
                    self._hole_segment_marker = self._segment_filename + '.hole'
                    count += 1
            if count < 3:
                if self._recording_requested:
                    raise AssertionError

    def cleanupTempFolder(self):
        conf = config.Config()
        now = time.time()
        dir = f'{conf.INGEST_DATADIR}/tmp'
        for fn in os.listdir(dir):
            pth = f'{dir}/{fn}'
            if os.path.isfile(pth):
                if fn.endswith('.ts') or fn.endswith('.concat'):
                    age = now - os.path.getmtime(pth)
                    if age >= 10 * 60: # 10 minutes
                        logger.info(f"remove old temp file 'tmp/{fn}'")
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
        self._hole_segment_marker = None
        self._current_cmd_log_level = 'INFO'
        try:
            conf = config.Config()
            os.chdir(f"{conf.INGEST_DATADIR}")
            proc = await asyncio.create_subprocess_shell(self._command,
                stdin = asyncio.subprocess.DEVNULL,
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
                    logger.bind(name='[from-cmd]').log(log_level, line)
                if i > 100:
                    self.cleanupTempFolder()
                    i = 0
                i += 1
            returncode = await proc.wait()
            logger.log(self._current_cmd_log_level, f'command exits with returncode {returncode}')
        finally:
            self.markHoleSegment()
            self._proc = None
            self._number_of_failed_records += 1
            await self.pushStatus()
            self.checkFatalAtStartup()

    def checkFatalAtStartup(self, msg=''):
        duration = (datetime.now() - self._service_start_time).total_seconds()
        if not (5 < duration < 10):
            return
        rate = self._number_of_failed_records / duration
        if rate < 0.6:
            return
        logger.error("too many record/halt cycles at startup")
        self._background_task.cancel()
        if self._aborter:
            self._aborter.abort()
        else:
            sys.exit(-1)

    def markHoleSegment(self):
        if self._hole_segment_marker is None:
            return
        logger.warning(f"put hole segment marker: {self._hole_segment_marker!r}")
        with open(f'{self._hole_segment_marker}','w') as f:
            f.write('')

    def requestRecording(self):
        self._recording_requested = True

    def requestHalt(self):
        self._number_of_failed_records -= 1
        self._recording_requested = False
        self._current_cmd_log_level = 'INFO'
        if self._proc is None:
            return
        parent = psutil.Process(self._proc.pid)
        children = parent.children(recursive=True)
        for pid in [self._proc.pid] + [child.pid for child in children]:
            os.kill(pid, signal.SIGTERM)
        self._proc = None

    def runBackgroundTaskDone(self, future):
        if future.cancelled():
            return
        future.result()
        raise AssertionError("run() done without error")

    async def stop(self):
        message = "stopping ingest service"
        logger.info(message)
        self.requestHalt()
        await self.pushStatus()
        for ws in list(self._status_websockets):
            await ws.close(code=WSCloseCode.GOING_AWAY, message=message)
        await asyncio.sleep(1)
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
                            self.requestRecording()
                            await self.pushStatus()
                            returned_msg = "ok"
                        else:
                            returned_msg = "state error: curently recording"
                    elif msg.data == 'halt':
                        if self._recording_requested:
                            self.requestHalt()
                            await self.pushStatus()
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
        sts['segment_filename'] = self._segment_filename
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


class IngestTimeLine:
    NAME_PATTERN = r"^[A-Za-z0-9_-]+$"
    PROTECTED_NAMES = set(['glob'])

    @classmethod
    def checkName(cls, name):
        if not re.fullmatch(cls.NAME_PATTERN, name):
            raise AssertionError(f'{name} is not a valid timeline name')

    @classmethod
    def loadNames(self):
        EXT = '.json'
        names = []
        conf = config.Config()
        for bn in os.listdir(f'{conf.INGEST_DATADIR}/timelines'):
            if bn.endswith(EXT):
                names.append(bn[:-len(EXT)])
        return names

    @classmethod
    def loadInstances(cls):
        instances = {}
        instances['glob'] = IngestTimeLine(name='glob')
        for name in cls.loadNames():
            tl = IngestTimeLine(name=name)
            instances[name] = tl
        return instances

    def __init__(self, *args, **kwargs):
        self.init(*args,**kwargs)

    def getJSONFilename(self):
        conf = config.Config()
        name = self._name
        return f'{conf.INGEST_DATADIR}/timelines/{name}.json'

    def init(self, name, readonly=False, begin=None, duration=None, load=True):
        self.checkName(name)
        self._name = name
        conf = config.Config()
        all_segment_filenames = glob.glob(f"{conf.INGEST_DATADIR}/segment_*.ts*")
        all_segment_filenames.sort()
        segments = {}
        for fn in all_segment_filenames:
            seg = IngestSegment.fromFileName(fn)
            segments[seg.begin] = seg
        if len(segments) > 0:
            first_seg = next(iter(segments.values()))
            last_seg = next(reversed(segments.values()))
        if begin is None:
            if len(segments) > 0:
                begin = first_seg.begin
            else:
                begin = datetime.combine(datetime.today(), datetime.min.time())
        if duration is None:
            if len(segments) > 0:
                duration = last_seg.begin - first_seg.begin + last_seg.duration
            else:
                duration = timedelta(seconds=0)
        if load and os.path.exists(self.getJSONFilename()):
            with open(self.getJSONFilename(), 'r') as f:
                d = json.loads(f.read())
            begin = datetime.fromisoformat(d['begin'])
            duration = timedelta(seconds=d['duration'])
        for seg in list(segments.values()):
            if (seg.begin + seg.duration) < begin:
                del segments[seg.begin]
            elif seg.begin >= (begin + duration):
                del segments[seg.begin]
        if len(segments) > 0:
            first_seg = next(iter(segments.values()))
            last_seg = next(reversed(segments.values()))
            end = (begin + duration)
            seg_end =(last_seg.begin + last_seg.duration)
            if begin > first_seg.begin:
                first_seg.inpoint = begin - first_seg.begin
            if seg_end > end:
                last_seg.outpoint = last_seg.duration - (seg_end - end)
        self._begin = begin
        self._duration = duration
        self._segments = segments

    @property
    def name(self):
        return self._name

    @property
    def begin(self):
        return self._begin

    @property
    def end(self):
        return self._begin + self._duration

    @property
    def duration(self):
        return self._duration

    @property
    def segments(self):
        return copy.copy(self._segments)

    def lookupSegmentFromTimestamp(self, timestamp):
        for seg in self._segments.values():
            if (seg.begin <= timestamp <= seg.end):
                return seg
        raise LookupError

    def getNumberOfHoles(self):
        num_holes = 0
        for seg in self._segments.values():
            if seg.hole:
                num_holes += 1
        return num_holes

    def advance(self, *, truncate=None):
        if truncate is None:
            truncate = timedelta(seconds=0)
        duration = self._duration + truncate
        begin = self._begin + duration - truncate
        self.init(self._name, begin=begin, duration=duration, load=False)

    def reset(self):
        duration = self._duration
        begin = None
        self.init(self._name, begin=begin, duration=duration, load=False)

    def rename(self, name):
        duration = self._duration
        begin = self._begin
        self.init(name, begin=begin, duration=duration, load=False)

    def save(self):
        name = self._name
        if name in self.PROTECTED_NAMES:
            raise AssertionError(f'timeline {name!r} cannot be altered')
        d = dict(
            begin = self._begin.isoformat(),
            duration = self._duration.total_seconds(),
        )
        with open(self.getJSONFilename(), 'w') as f:
            f.write(json.dumps(d) + '\n')

    def remove(self):
        name = self._name
        if name in self.PROTECTED_NAMES:
            raise AssertionError(f'timeline {name!r} cannot be removed')
        os.remove(self.getJSONFilename())

    def slices(self):
        segments = []
        slices_ = []
        for seg in self._segments.values():
            segments.append(seg)
            if seg.hole:
                slices_.append(IngestTimeSlice(timeline=self, segments=segments))
                segments = []
        if len(segments):
            slices_.append(IngestTimeSlice(timeline=self, segments=segments))
        if len(slices_):
            slices_[-1].setLast()
        return slices_

class IngestSegment:
    @staticmethod
    def fromFileName(filename):
        basename = os.path.basename(filename)
        m = re.match(SEGMENT_PATTERN, basename)
        if not m:
            raise AssertionError(f'cannot parse segment filename: {basename!r}')
        begin = datetime.strptime(m.group(1), SEGMENT_DATETIME_FORMAT)
        duration = timedelta(seconds=float(m.group(2)))
        if m.group(3):
            hole = True
            L = len(m.group(3))
            basename = basename[:-L]
            filename = filename[:-L]
        else:
            hole = False
        return IngestSegment(filename=filename, basename=basename, begin=begin, duration=duration,
            hole=hole)

    def __init__(self, *,filename, basename, begin, duration, inpoint=None, outpoint=None, hole=False):
        self.filename = filename
        self.basename = basename
        self.begin = begin
        self.duration = duration
        self.inpoint = inpoint
        self.outpoint = outpoint
        self.hole = hole

    @property
    def end(self):
        return self.begin + self.duration

    @property
    def effective_duration(self):
        duration = self.duration
        if self.inpoint is None:
            inpoint = timedelta(seconds=0)
        else:
            inpoint = self.inpoint
        if self.outpoint is None:
            outpoint = duration
        else:
            outpoint = self.outpoint
        return outpoint - inpoint

    def __repr__(self):
        s = f'<{self.__class__.__name__} at {hex(id(self))}'
        for k,v in self.__dict__.items():
            s += f' {k}={v!r}'
        s += '>'
        return s


class IngestTimeSlice:
    def __init__(self, *, timeline, segments):
        self._timeline = timeline
        self._segments = copy.copy(segments)
        self._last = False
        assert len(self._segments) > 0
        if len(self._segments) >= 2:
            assert self._segments[0].outpoint is None
            assert self._segments[-1].inpoint is None
            for seg in self._segments[1:-1]:
                assert seg.outpoint is None
                assert seg.inpoint is None

    def setLast(self):
        self._last = True

    @property
    def last(self):
        return self._last

    @property
    def segments(self):
        return copy.copy(self._segments)

    @property
    def begin(self):
        if len(self._segments) == 0:
            raise AssertionError
        first_seg = self._segments[0]
        return first_seg.begin

    @property
    def end(self):
        if len(self._segments) == 0:
            raise AssertionError
        last_seg = self._segments[-1]
        return last_seg.begin + last_seg.duration

    @property
    def duration(self):
        duration = timedelta(seconds=0)
        for seg in self._segments:
            duration += seg.duration
        return duration

    @property
    def effective_duration(self):
        duration = timedelta(seconds=0)
        for seg in self._segments:
            duration += seg.effective_duration
        return duration

    @property
    def first_inpoint(self):
        return self._segments[0].inpoint

    @property
    def last_outpoint(self):
        return self._segments[-1].outpoint

    def generateConcatContent(self, *, with_inoutpoints=False):
        s = ''
        if with_inoutpoints:
            start_line =''
        else:
            start_line ='#'
        for seg in self._segments:
            s += f"file '{seg.filename}'\n"
            if seg.inpoint:
                s += f'{start_line} inpoint {seg.inpoint.total_seconds()}\n'
            if seg.outpoint:
                s += f'{start_line} outpoint {seg.outpoint.total_seconds()}\n'
            s += '\n'
        return s

    def concatFile(self, *, delete=True, with_inoutpoints=False):
        conf = config.Config()
        tl = self._timeline
        f = tempfile.NamedTemporaryFile(dir=f"{conf.INGEST_DATADIR}/tmp/", prefix=f'{tl.name}_', suffix=".concat", mode='w', delete=delete)
        content = self.generateConcatContent(with_inoutpoints=with_inoutpoints)
        f.write(content)
        f.flush()
        return f


TLTOOL_ACTIONS = {}


def TLtool_action(*names):
    def inner(obj):
        for n in names:
            TLTOOL_ACTIONS[n]=obj
    return inner


class IngestTimeLineTool:
    class ArgumentParser(argparse.ArgumentParser):
        def __init__(self):
            actions = '|'.join(TLTOOL_ACTIONS)
            super().__init__(usage=f'%(prog)s <{actions}> [timeline-names] <options>')
            self.add_argument('-d','--duration', dest='duration', default="0s", help="set timeline duration")
            self.add_argument('-s','--slice-index', dest='slice_index', default=None, type=int, help="set slice index")

        def parse_args(self, args):
            prog = args[0]
            ns,args = super().parse_known_args(args[1:])
            ns.prog = prog
            ns.action = None
            ns.largs = []
            ns.rargs = []
            xargs = ns.largs
            for a in args:
                if ns.action is None:
                    if a not in TLTOOL_ACTIONS:
                        self.error(f'invalid action {a!r}')
                    else:
                        ns.action = a
                elif a == '--':
                    xargs = ns.rargs
                else:
                    xargs.append(a)
            if ns.action is None:
                self.error('no action secified')
            return ns

    def __init__(self, args):
        p = self.ArgumentParser()
        self._ns = p.parse_args(args)
        self._argparser = p

    def __call__(self):
        ns = self._ns
        f = TLTOOL_ACTIONS[ns.action]
        f(self)

    @TLtool_action('rm','remove')
    def remove(self):
        ns = self._ns
        for name in ns.largs:
            self.ensureName(name, 'existing')
            tl = IngestTimeLine(name=name)
            tl.remove()

    def getName(self, idx):
        ns = self._ns
        try:
            name = ns.largs[idx]
        except IndexError:
            self.error('please specify a valid timeline name')
        return name

    def error(self, msg):
        self._argparser.error(msg)

    def ensureName(self, name, mode):
        exists = (name in IngestTimeLine.loadNames()) or (name in IngestTimeLine.PROTECTED_NAMES)
        if mode not in ('existing', 'not-existing'):
            raise AssertionError
        if exists and mode=='not-existing':
            self.error(f'timeline {name!r} already exists')
        if not exists and mode=='existing':
            self.error(f'timeline {name!r} does not exist')

    @TLtool_action('create')
    def create(self):
        ns = self._ns
        name = self.getName(0)
        self.ensureName(name, 'not-existing')
        duration = timedelta(seconds=timeparse(ns.duration))
        begin = None
        tl = IngestTimeLine(name=name, begin=begin, duration=duration)
        tl.save()

    @TLtool_action('adv', 'advance')
    def advance(self):
        name = self.getName(0)
        self.ensureName(name, 'existing')
        tl = IngestTimeLine(name=name)
        tl.advance()
        tl.save()

    @TLtool_action('reset')
    def reset(self):
        name = self.getName(0)
        self.ensureName(name, 'existing')
        tl = IngestTimeLine(name=name)
        tl.reset()
        tl.save()

    @TLtool_action('cp','copy')
    def copy(self):
        src_name = self.getName(0)
        dst_name = self.getName(1)
        self.ensureName(src_name, 'existing')
        self.ensureName(dst_name, 'not-existing')
        tl = IngestTimeLine(name=src_name)
        tl.rename(dst_name)
        tl.save()

    @TLtool_action('ed','edit')
    def edit(self):
        name = self.getName(0)
        tl = IngestTimeLine(name=name)
        tl.save()
        cmd = f"{os.getenv('EDITOR')} {tl.getJSONFilename()}"
        cmd = shlex.split(cmd)
        os.execvp(cmd[0],cmd)
        raise AssertionError('execvp() failed')

    @TLtool_action('ls','list')
    def list(self):
        table = Table()
        table.add_column("NAME")
        table.add_column("BEGIN")
        table.add_column("END")
        table.add_column("DURATION")
        table.add_column("NUM_HOLES")
        for name, tl in IngestTimeLine.loadInstances().items():
            if tl.duration.total_seconds() == 0:
                duration = "0s"
            else:
                duration = str(tl.duration)
            table.add_row(name, tl.begin.isoformat(), tl.end.isoformat(), duration, f'{tl.getNumberOfHoles()}')
        print(table)

    @TLtool_action('sl','slices')
    def slices(self):
        table = Table()
        headers = ["SLICE_ID/SEGMENT_BASENAME", "INPOINT", "OUTPOINT", "EFFECTIVE_DURATION"]
        for hdr in headers:
            table.add_column(hdr)
        seprator = [''] * len(headers)
        name = self.getName(0)
        self.ensureName(name, 'existing')
        tl = IngestTimeLine(name=name)
        for i,slice in enumerate(tl.slices()):
            table.add_row(*seprator)
            table.add_row(f'[cyan]slice #{i}[/cyan]','','',f'[cyan]{slice.effective_duration}[/cyan]')
            for seg in slice.segments:
                table.add_row(seg.basename,f'{seg.inpoint}',f'{seg.outpoint}',f'{seg.effective_duration}')
        print()
        print(table)

    @TLtool_action('concat')
    def concat(self):
        ns = self._ns
        name = self.getName(0)
        self.ensureName(name, 'existing')
        tl = IngestTimeLine(name=name)
        slice = list(tl.slices())[ns.slice_index]
        content = slice.generateConcatContent()
        print(content)
