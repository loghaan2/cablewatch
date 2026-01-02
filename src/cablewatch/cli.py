import asyncio
import signal
import sys
import os
import subprocess
import re
import select
import fcntl
from datetime import datetime, timedelta
import wave
import requests
from rich import print
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
async def main_services():
    loghlp.setup()
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


# -----------------------------------------------------------------------------
# some examples using timeline
# -----------------------------------------------------------------------------

TLEX_CROP = 'crop=890:54:68:ih-145'


def tlex_extract_skeleton():
    timeline = ingest.IngestTimeLine(name="skeleton", duration=timedelta(minutes=3))
    try:
        for i,slice in enumerate(timeline.slices()):
            with slice.concatFile() as concat:
                print(f'[red]* SLICE #{i} - begin={slice.begin} duration={slice.effective_duration}[/red]')
                cmd = f'ffmpeg -f concat -safe 0 -i {concat.name}'
                cmd += ' -f null -'
                print(f'[red]* {cmd}[/red]')
                subprocess.run(cmd, shell=True, check=True)
    finally:
        timeline.advance()
        timeline.save()


def tlex_play_slice():
    timeline_name = sys.argv[1]
    slice_index = int(sys.argv[2])
    timeline = ingest.IngestTimeLine(name=timeline_name)
    slice = list(timeline.slices())[slice_index]
    with slice.concatFile() as concat:
        cmd = f'ffplay -autoexit -f concat -safe 0 {concat.name}'
        p = subprocess.run(cmd, shell=True)
        sys.exit(p.returncode)


def tlex_detect_freeze_in_slices():
    timeline_name = sys.argv[1]
    timeline = ingest.IngestTimeLine(name=timeline_name)
    freezedetect = 'freezedetect=n=0.003:d=2'
    unix_ts_fh = open(f'{timeline_name}-freezedetect.txt','w')
    for i,slice in enumerate(timeline.slices()):
        with slice.concatFile() as concat:
            print(f'[red]* SLICE #{i}[/red]')
            cmd = f'ffmpeg -f concat -safe 0 -i {concat.name}'
            cmd += f' -vf {TLEX_CROP},{freezedetect} '
            cmd += ' -f null -'
            print(f'[red]* {cmd}[/red]')
            p = subprocess.Popen(
                cmd,
                shell = True,
                stdout = subprocess.PIPE,
                stderr = subprocess.STDOUT,
            )
            start = None
            end = None
            duration = 0
            while True:
                ln = p.stdout.readline()
                if len(ln) == 0:
                    break
                ln = ln.decode()
                if ln[-1] == '\n':
                    ln=ln[:-1]
                print(ln)
                m = re.search(r'avfi.freezedetect.freeze_start: (.+)$', ln)
                if m:
                    start = float(m.group(1))
                m = re.search(r'avfi.freezedetect.freeze_duration: (.+)$', ln)
                if m:
                    duration = float(m.group(1))
                m = re.search(r'avfi.freezedetect.freeze_end: (.+)$', ln)
                if m:
                    end = float(m.group(1))
                if start and duration and end:
                    ts_start = slice.begin + timedelta(seconds=start)
                    ts_end = slice.begin + timedelta(seconds=end)
                    ts_mid = slice.begin + timedelta(seconds=start+duration/2)
                    unix_ts_mid = ts_mid.strftime('%s')
                    unix_ts_fh.write(f'{unix_ts_mid}\n')
                    unix_ts_fh.flush()
                    fields = f"start={start:.2f} duration={duration:.2f}s ts_start='{ts_start}' ts_end='{ts_end}' ts_mid='{ts_mid}' unix_ts_mid={unix_ts_mid}"
                    print(f'[red]* freeze detected: {fields}[/red]')
                    duration = 0
                    start = None
                    end = None
            print()


def tlex_apply_ocr_on_frames():
    timeline = ingest.IngestTimeLine(name='glob')
    for a in sys.argv[1:]:
        unix_timestamp = int(a)
        timestamp = datetime.fromtimestamp(unix_timestamp)
        seg = timeline.lookupSegmentFromTimestamp(timestamp)
        offset = timestamp - seg.begin
        cmd = f'ffmpeg -y -i {seg.filename} '
        cmd += f"-vf {TLEX_CROP} "
        cmd += f"-ss {offset} -vframes 1 frame_{unix_timestamp}.png"
        print(f'[red]* {cmd}[/red]')
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cmd = f"tesseract -l fra+eng frame_{unix_timestamp}.png -" # " hocr"
        print(f'[red]* {cmd}[/red]')
        p = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE)
        print(f'[green]{p.stdout.decode()}[green]')


def tlex_process_slice_audio():
    timeline_name = sys.argv[1]
    slice_index = int(sys.argv[2])
    timeline = ingest.IngestTimeLine(name=timeline_name)
    slice = list(timeline.slices())[slice_index]
    sample_rate = 16000
    sample_width = 2
    num_channels = 1 # mono
    with slice.concatFile() as concat:
        fdr, fdw = os.pipe()
        cmd = f'ffmpeg -f concat -safe 0 -i {concat.name}'
        cmd += ' -af silencedetect=noise=-30dB:d=0.5'
        cmd += f' -vn -ac 1 -ar {sample_rate} -f wav '
        cmd += ' pipe:1 '
        print(f'[red]* {cmd}[/red]')
        proc = subprocess.Popen(
            cmd,
            shell = True,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
        )
        poller = select.poll()
        active_fds = {proc.stdout.fileno(), proc.stderr.fileno()}
        for fd in active_fds:
            poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        wav_buffer =b''
        wav_header = None
        start = None
        end = None
        duration = 0
        cut_positions = []
        wav_buffer_size = 0
        wav_buffer_offset = 0
        count = 0
        while len(active_fds) > 0 or len(cut_positions) > 0:
            for fd, ev in poller.poll():
                if ev & select.POLLERR:
                    raise AssertionError
                elif ev & select.POLLHUP:
                    poller.unregister(fd)
                    active_fds.remove(fd)
                    if fd == proc.stderr.fileno():
                        cut_positions.append(wav_buffer_size)
                elif ev & select.POLLIN:
                    if fd == proc.stderr.fileno(): # ffmpeg log output
                        ln = proc.stderr.readline()
                        if ln.endswith(b'\n'):
                            ln = ln[:-1]
                        ln = ln.decode()
                        print(ln)
                        m = re.search(r'silence_start: (.+)$', ln)
                        if m:
                            start = float(m.group(1))
                        m = re.search(r'silence_end: (.+) \| silence_duration: (.+)$', ln)
                        if m:
                            end = float(m.group(1))
                            duration = float(m.group(2))
                        if start and duration and end:
                            print(f'[red] silencedetect: #{count} start={start:.2f}s duration={duration:.2f}s end={end:.2f}s[/red]')
                            pos = int((start+duration/2) * sample_rate) * sample_width
                            cut_positions.append(pos)
                            duration = 0
                            start = None
                            end = None
                            count += 1
                        print(ln)
                    else: # ffmpeg wav output
                        if wav_header is None:
                            wav_header = os.read(fd, 44)
                        else:
                            wav_chunk = os.read(fd, 256)
                            wav_buffer += wav_chunk
                            wav_buffer_size += len(wav_chunk)
            try:
                pos = cut_positions[0]
            except IndexError:
                continue
            if pos <= wav_buffer_size:
                pos = cut_positions.pop(0)
                with wave.open(f'{timeline_name}_{slice_index}_{pos:08d}.wav', 'wb') as wav:
                    wav.setnchannels(num_channels)
                    wav.setsampwidth(sample_width)
                    wav.setframerate(sample_rate)
                    wav_frames = wav_buffer[:pos-wav_buffer_offset]
                    wav_buffer = wav_buffer[pos-wav_buffer_offset:]
                    wav_buffer_offset = pos
                    wav.writeframes(wav_frames)
