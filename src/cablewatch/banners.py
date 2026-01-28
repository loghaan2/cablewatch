import subprocess
import re
import select
import sys
import os
import io
import math
import copy
import json
import glob
from datetime import datetime, timedelta
from loguru import logger
from rich.console import Console
from PIL import Image, ImageOps
import pytesseract
from cablewatch import config, ingest
from cablewatch.decorators import ToolDecorator


def main():
    tool = BannersTool(sys.argv, action='silver')
    tool()


def readline(fd):
    line = b''
    while True:
        ch = os.read(fd, 1)
        if len(ch) == 0:
            return ''
        if ch==b'\r' or ch==b'\n':
            return line.strip().decode()
        else:
            line += ch


DATETIME_FORMAT = "%Y%m%d_%Hh%Mm%S"
PNG_BASENAME_FORMAT = '{kind}_{datetime}.png'
JSON_BASENAME_FORMAT = '{datetime}_{duration_ms}ms.json'
JSON_BASENAME_PATTERN = r'^(.+)_(.+)ms(\.json)?$'


BANNERS_CHARACTERISTICS = dict(
    topic = {
        "detect-crop": "crop=890:48:68:577",
        "freeze": "freezedetect=n=0.002:d=3",
        "bg_color": (0,0,0), #black
        "dynamic": False,
        "invert": True,
    },
    programtitle = {
        "detect-crop": "crop=229:81:986:637",
        "freeze": "freezedetect=n=0.002:d=5",
        "bg_color": (253,193,0), #some kind of yellow
        "dynamic": False,
        "invert": False,
    },
    speaker = {
        "detect-crop": "crop=83:30:69:536",
        "retrieve-crop": "crop=886:62:69:504",
        "freeze": "freezedetect=n=0.002:d=2",
        "bg_color": (255,255,255), #white
        "dynamic": True,
        "invert": False,
    },
)


def score_color_distance(col1, col2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(col1[:3], col2[:3])))


tooldec = ToolDecorator()

class BannersTool(tooldec.BaseTool):
    TIMELINE_NAME = 'banners'
    PNG_CHUNK_SIZE = 256
    LOCAL_COPY = False
    SCORE_MAX = 20

    @tooldec.action('init')
    def init(self):
        ns = self._ns
        tl = ingest.IngestTimeLine(self.TIMELINE_NAME, begin=ns.begin, duration=ns.duration)
        tl.save()
        logger.info(f'timeline created: {tl.name!r} begin={tl.begin.strftime(DATETIME_FORMAT)!r} duration={tl.duration.total_seconds()!r}')

    @tooldec.action('extract')
    def extract(self):
        try:
            tl = ingest.IngestTimeLine.load(self.TIMELINE_NAME)
        except KeyError:
            logger.warning(f'cannot open timeline {self.TIMELINE_NAME!r} => nothing to do')
            return
        if not tl.isReady():
            logger.warning(f"timeline {self.TIMELINE_NAME!r} currently not ready => nothing to do")
            return
        logger.info(f'timeline before: {tl.name!r} begin={tl.begin.strftime(DATETIME_FORMAT)!r} duration={tl.duration.total_seconds()!r}')
        try:
            for slice in tl.slices():
                rows = []
                for kind in BANNERS_CHARACTERISTICS.keys():
                    logger.info(f'detect banners of kind {kind!r}...')
                    detected_freezes = self.detectFreezes(slice, kind)
                    for i,freeze in enumerate(detected_freezes):
                        logger.info(f'interpret banner {kind!r} {i+1}/{len(detected_freezes)}...')
                        pth, frame = self.retrieveFrame(slice, kind, freeze)
                        content = self.interpretFrame(kind, freeze, pth, frame)
                        if content is None:
                            continue
                        begin = (slice.begin + timedelta(seconds=freeze['start'])).strftime(DATETIME_FORMAT)
                        duration = freeze['duration']
                        rows.append(dict(kind=kind,begin=begin,duration=duration,content=content))
                conf = config.Config()
                basename = JSON_BASENAME_FORMAT.format(datetime=slice.begin.strftime(DATETIME_FORMAT), duration_ms=int(slice.effective_duration.total_seconds()*1000))
                rows.sort(key=lambda d: d['begin'])
                with open(f'{conf.BANNERS_DATADIR}/{basename}', 'w') as f:
                    f.write(json.dumps(rows, indent=4))
        except:
            raise
        finally:
            # move timeline
            ns = self._ns
            if not ns.stay:
                tl.advance()
                tl.save()
            logger.info(f'timeline after: {tl.name!r} begin={tl.begin.strftime(DATETIME_FORMAT)!r} duration={tl.duration.total_seconds()!r}')

    def detectFreezes(self, slice, kind):
        characs = BANNERS_CHARACTERISTICS[kind]
        extra_filter = f"{characs['detect-crop']},{characs['freeze']}"
        inputs_and_filter = slice.generateConcatCommand(only='video', extra_filter=extra_filter)
        cmd = ['ffmpeg'] + inputs_and_filter + ['-f', 'null', '-']
        logger.info(f'run {" ".join(cmd)!r}')
        proc = subprocess.Popen(
            cmd,
            shell = False,
            stdin = subprocess.DEVNULL,
            stdout = subprocess.PIPE,
            stderr = subprocess.STDOUT,
        )
        fd = proc.stdout.fileno()
        detected_freezes = []
        freeze = {}
        while True:
            ln = readline(fd)
            if len(ln) == 0:
                logger.info("ffmpeg log output EOF")
                break
            if ln.endswith('\n'):
                ln = ln[:-1]
            logger.bind(name='[ffmpeg]').debug(ln)
            for k in 'start', 'duration', 'end':
                m = re.search(fr'freezedetect\.freeze_{k}: (\d+\.\d+)', ln)
                if not m:
                    continue
                freeze[k] = float(m.group(1))
            if len(freeze)==3:
                logger.info(f'banner frame {kind!r} detected at {freeze!r}s')
                detected_freezes.append(copy.copy(freeze))
                freeze.clear()
        logger.info(f'finally {len(detected_freezes)} freeze(s) detected')
        return detected_freezes

    def retrieveFrame(self, slice, kind, freeze):
        characs = BANNERS_CHARACTERISTICS[kind]
        tsec = freeze['start'] + freeze['duration']/2
        logger.info(f'retrieve banner frame {kind!r} at {tsec}s')
        crop = characs.get('retrieve-crop', characs['detect-crop'])
        extra_filter = f"{crop},select='gte(t,{tsec})',setpts=N/FRAME_RATE/TB"
        inputs_and_filter = slice.generateConcatCommand(only='video', extra_filter=extra_filter)
        cmd = ['ffmpeg'] + inputs_and_filter + ['-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-']
        logger.info(f'run {" ".join(cmd)!r}')
        proc = subprocess.Popen(
            cmd,
            shell = False,
            stdin = subprocess.DEVNULL,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
        )
        poller = select.poll()
        active_fds = {proc.stdout.fileno(), proc.stderr.fileno()}
        png_frame = b''
        for fd in active_fds:
            poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
        while len(active_fds) > 0:
            for fd, ev in poller.poll():
                if ev & select.POLLERR:
                    raise AssertionError
                elif ev & (select.POLLIN | select.POLLHUP):
                    if fd == proc.stderr.fileno(): # ffmpeg log output
                        ln = readline(fd)
                        if len(ln) == 0:
                            logger.info("ffmpeg log output EOF")
                            poller.unregister(fd)
                            active_fds.remove(fd)
                            break
                        if ln.endswith('\n'):
                            ln = ln[:-1]
                        logger.bind(name='[ffmpeg]').debug(ln)
                    else: # ffmpeg PNG output
                        png_chunk = os.read(fd, self.PNG_CHUNK_SIZE)
                        if len(png_chunk) == 0:
                            logger.info("ffmpeg PNG output EOF")
                            poller.unregister(fd)
                            active_fds.remove(fd)
                            break
                        png_frame += png_chunk
        conf = config.Config()
        t = slice.begin + timedelta(seconds=tsec)
        basename = PNG_BASENAME_FORMAT.format(kind=kind, datetime=t.strftime(DATETIME_FORMAT))
        ns = self._ns
        if ns.local_copy:
            png_pth = f'{conf.BANNERS_DATADIR}/{basename}'
            with open(png_pth, 'wb') as f:
                f.write(png_frame)
            logger.info(f"banner frame saved in {png_pth}")
        else:
            png_pth = None
        return png_pth, png_frame

    def interpretFrame(self, kind, freeze, png_pth, png_frame):
        tsec = freeze['start'] + freeze['duration']/2
        logger.info(f'interpret banner frame {kind!r} at {tsec}s')
        f = io.BytesIO(png_frame)
        try:
            img = Image.open(f)
        except Exception:
            logger.error(f'cannot open image - size={len(png_frame)} byte(s)')
            return None
        logger.info(f'frame geometry is {img.width}x{img.height}')
        characs = BANNERS_CHARACTERISTICS[kind]
        if characs['dynamic']:
            logger.info(f'dynamic mode for {kind!r} guessing new geometry')
            top_y = img.height - 1
            bottom_y = img.height - 1
            while top_y >= 1:
                col = img.getpixel((0,top_y-1))
                score = score_color_distance(col, characs['bg_color'])
                if score > self.SCORE_MAX:
                    break
                top_y -= 1
            x = 0
            while x < img.width:
                top_col = img.getpixel((x, top_y))
                top_score = score_color_distance(top_col, characs['bg_color'])
                bottom_col = img.getpixel((x, bottom_y))
                bottom_score = score_color_distance(bottom_col, characs['bg_color'])
                if (top_score > self.SCORE_MAX) and (bottom_score > self.SCORE_MAX):
                    break
                x += 1
            dynamic_img = img.crop((0,top_y,x,img.height-1))
            logger.info(f'new frame geometry is {dynamic_img.width}x{dynamic_img.height}')
            if dynamic_img.width == 0:
                return None
            if dynamic_img.height == 0:
                return None
            if png_pth:
                dynamic_img.save(f'{os.path.splitext(png_pth)[0]}_dynamic.png')
            img = dynamic_img
        else:
            for xy in [(2,2), (img.width-2,img.height-2)]:
                try:
                    col = img.getpixel(xy)
                except IndexError:
                    return None
                score = score_color_distance(col, characs['bg_color'])
                if score > self.SCORE_MAX:
                    return None
        if characs['invert']:
            img = img.convert("L")
            img = ImageOps.invert(img)
            if png_pth:
                img.save(f'{os.path.splitext(png_pth)[0]}_invert.png')
        content = pytesseract.image_to_string(img, lang='fra', config="--psm 6 --oem 3")
        logger.info(f'interpret banner frame {kind!r} as {content!r}')
        return content

    @tooldec.action('bronze', 'silver')
    def view(self):
        console = Console(force_terminal=True)
        ns = self._ns
        for d in BannersQuery(begin=ns.begin, end=ns.end, layer=ns.action):
            if 'begin' in d:
                d['begin'] = d['begin'].strftime(DATETIME_FORMAT)
            console.print(d)


class BannersQuery:
    def __init__(self, *, begin, end, layer="silver", logger=None):
        if (begin is None) or (end is None):
            raise AssertionError
        conf = config.Config()
        self._begin = begin
        self._end = end
        self._logger = logger
        self._layer = layer
        all_sequences_filenames = glob.glob(f"{conf.BANNERS_DATADIR}/*.json")
        all_sequences_filenames.sort()
        sequences = {}
        for fn in all_sequences_filenames:
            seq = BannersSequence.fromFileName(fn)
            sequences[seq.begin] = seq
        self._sequences = sequences

    def inTimeRange(self, d):
        end = d['begin'] + timedelta(seconds=d['duration'])
        if end < self._begin:
            return False
        if d['begin'] > self._end:
            return False
        return True

    def __iter__(self):
        f = getattr(self, self._layer)
        yield from f()

    def bronze(self):
        for seq in self._sequences.values():
            for d in seq.data:
                d = copy.copy(d)
                d['begin'] = datetime.strptime(d['begin'], DATETIME_FORMAT)
                if self.inTimeRange(d):
                    yield d

    def silver(self):
        for d in self.bronze():
            d = copy.copy(d)
            if d['content'].endswith('\n'):
                d['content'] = d['content'][:-1]
            d['content'] = d['content'].replace('\n',' ')
            if len(d['content']) == 0:
                continue
            yield d


class BannersSequence:
    @classmethod
    def fromFileName(cls, filename):
        basename = os.path.basename(filename)
        m = re.match(JSON_BASENAME_PATTERN, basename)
        if not m:
            raise AssertionError(f'cannot parse result filename: {basename!r}')
        begin = datetime.strptime(m.group(1), DATETIME_FORMAT)
        duration = timedelta(seconds=float(m.group(2))/1000)
        return cls(filename=filename, basename=basename, begin=begin, duration=duration)

    def __init__(self, *,filename, basename, begin, duration):
        self.filename = filename
        self.basename = basename
        self.begin = begin
        self.duration = duration
        with open(self.filename, 'r') as f:
            self.data = json.loads(f.read())

    @property
    def end(self):
        return self.begin + self.duration

    def __repr__(self):
        s = f'<{self.__class__.__name__} at {hex(id(self))}'
        for k,v in self.__dict__.items():
            if k=='data':
                continue
            else:
                s += f' {k}={v!r}'
        s += '>'
        return s
