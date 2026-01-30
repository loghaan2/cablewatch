import os
import fnmatch
import asyncio
import aiohttp
import sys
import re
import unicodedata
import collections
from datetime import datetime, timedelta, time
from aiohttp import web
from loguru import logger
from rapidfuzz import fuzz
import json
from cablewatch import config, loghlp, speech, banners
from cablewatch.decorators import http_get, ToolDecorator


class PapersService:
    def __init__(self, *, http_service):
        http_service.addDecoratedRoutes(self)

    async def start(self):
        pass

    async def stop(self):
        pass

    def makeFilter(self, request: web.Request):
        try:
            filter = request.match_info["filter"]
        except KeyError:
            filter = '*'
        return filter

    async def makeList(self, filter: str):
        conf = config.Config()
        result = []
        for bn in os.listdir(conf.PAPERS_DATADIR):
            pth = os.path.join(conf.PAPERS_DATADIR, bn)
            if bn.startswith('.'):
                continue
            if os.path.isdir(pth):
                continue
            if not fnmatch.fnmatch(bn.lower(), filter.lower()):
                continue
            result.append(bn)
        result.sort()
        return result

    @http_get("/api/papers/list")
    @http_get("/api/papers/list/{filter}")
    async def handleList(self, request: web.Request) -> web.Response:
        filter = self.makeFilter(request)
        basenames = await self.makeList(filter)
        return web.json_response(basenames)

    @http_get("/api/papers/download/{index}")
    @http_get("/api/papers/download/{filter}/{index}")
    @http_get("/api/papers/view/{index}")
    @http_get("/api/papers/view/{filter}/{index}")
    async def handleDownload(self, request: web.Request) -> web.Response:
        conf = config.Config()
        filter = self.makeFilter(request)
        basenames = await self.makeList(filter)
        index = request.match_info["index"]
        def bad_index(index):
            return web.Response(text=f"Bad index: {index!r}", status=404)
        try:
            index = int(index)
        except ValueError:
            return bad_index(index)
        if index < 0:
            return bad_index(index)
        try:
            bn = basenames[index]
        except IndexError:
            return bad_index(index)
        resp = web.FileResponse(f'{conf.PAPERS_DATADIR}/{bn}')
        resp.headers.pop('Content-Disposition', None)
        if request.path.startswith('/api/papers/download/'):
            mode = 'attachment'
        else:
            mode = 'inline'
        resp.headers['Content-Disposition'] = f'{mode}; filename="{bn}"'
        return resp

    @http_get("/api/papers/download-archive")
    @http_get("/api/papers/download-archive/")
    @http_get("/api/papers/download-archive/{filter}")
    async def handleDownloadArchive(self, request: web.Request) -> web.Response:
        conf = config.Config()
        filter = self.makeFilter(request)
        basenames = await self.makeList(filter)
        archive_name = f'{datetime.now().strftime("%Y%m%d_%Hh%M")}_papers_{filter.encode().hex()}'
        resp = web.StreamResponse(
            headers = {
                "Content-Type": "application/gzip",
                "Content-Disposition": f'attachment; filename="{archive_name}.tar.gz"',
            }
        )
        await resp.prepare(request)
        cmd = f"tar zcvf - --transform 's|^|{archive_name}/|' {' '.join(basenames)}"
        logger.bind(name='[tar]').info(f'* {cmd}')
        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd = conf.PAPERS_DATADIR,
                stdin = asyncio.subprocess.DEVNULL,
                stdout = asyncio.subprocess.PIPE,
                stderr = asyncio.subprocess.PIPE,
            )
            while True:
                chunk, ln = await asyncio.gather(
                    proc.stdout.read(8192),
                    proc.stderr.readline(),
                )
                if len(chunk)==0 and len(ln)==0:
                    break
                if len(ln):
                    if ln.endswith(b'\n'):
                        ln = ln[:-1]
                    logger.bind(name='[tar]').info(f'  {ln.decode()}')
                if len(chunk):
                    await resp.write(chunk)
            await resp.write_eof()
        except aiohttp.client_exceptions.ClientConnectionResetError:
            logger.warning('client connection reset')
        except Exception:
            loghlp.log_exception(logger=logger, title='handleDownloadArchive()')
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            await proc.wait()
        return resp


def main():
    tool = PapersTool(args=sys.argv)
    tool()


tooldec = ToolDecorator()

class PapersTool(tooldec.BaseTool):
    TIMELINE_NAME = 'papers'

    @tooldec.action('gen','generate')
    def generate(self):
        ns = self._ns
        day = ns.begin.date()
        g = PapersGenerator(day)
        g()


class PapersGenerator:
    def __init__(self, day):
        self._begin = datetime.combine(day, time.min)
        self._end = datetime.combine(day, time.max)
        self._speaker_labels = collections.defaultdict(list)

    def sanitizeBasename(self, value: str, replacement: str = "-",  max_length: int = 255):
        value = unicodedata.normalize("NFKD", value)
        value = value.encode("ascii", "ignore").decode("ascii")
        value = re.sub(r'[\\/*?:"<>|]', replacement, value)
        value = re.sub(r"\s+", replacement, value)
        value = re.sub(rf"{re.escape(replacement)}+", replacement, value)
        value = value.strip(replacement + ".")
        if not value:
            value = "file"
        return value[:max_length]

    def __call__(self):
        pgm_current = None
        for d in banners.BannersQuery(begin=self._begin, end=self._end):
            if d['kind'] != 'programtitle':
                continue
            if (pgm_current is None):
                pgm_current = d
                continue
            score = fuzz.ratio(d['content'], pgm_current["content"])
            if score < 80:
                self.pgm(pgm_current['content'], begin=pgm_current['begin'], end=d['begin'])
                pgm_current = d
        if pgm_current:
            self.pgm(pgm_current['content'], begin=pgm_current['begin'], end=d['begin'])

    def pgm(self, title, begin, end):
        duration_mn = f'{int((end-begin).total_seconds()/60)}'
        j = {}
        j['title'] = title
        j['date'] = begin.strftime("%d/%m/%Y")
        j['begin'] = begin.strftime("%Hh%M")
        j['end'] = end.strftime("%Hh%M")
        j['duration'] = f'{duration_mn}mn'
        content = []
        j['content'] = content
        basename = f"{begin.strftime("%Y%m%d_%Hh%M")}__{title}"
        basename = self.sanitizeBasename(basename)
        conf = config.Config()
        previous_speaker = None
        text = ''
        topic = self.lookupTopic(begin)
        text_begin = begin
        for d in speech.SpeechQuery(begin=begin, end=end, last=dict(speaker=None, word='', timestamp=end)):
            speaker = d['speaker']
            if speaker != previous_speaker:
                J = {}
                if topic is not None:
                    J['topic'] = topic
                text = text.strip()
                J['timestamp'] = text_begin.strftime("%Hh%Mm%S")
                if len(text) > 0:
                    J['speaker'] = self.lookupSpeakerLabel(previous_speaker, text_begin, d['timestamp'])
                    cmd = f'cablewatch-ingest pipe -Tb {(text_begin+timedelta(seconds=15)).strftime("%Y%m%d_%Hh%Mm%S")} -Td 5mn|mpv - --no-terminal'
                    J['playback-cmd'] = cmd
                    J['text'] = text
                previous_speaker = speaker
                topic = self.lookupTopic(d['timestamp'])
                content.append(J)
                text = ''
                text_begin = d['timestamp']
            text += f' {d['word']}'
        with open(f'{conf.PAPERS_DATADIR}/{basename}.json','w') as f:
            f.write(json.dumps(j, indent=4))
        logger.info(f"{basename!r}.json written")

    def lookupSpeakerLabel(self, speaker, text_begin, text_end):
        for d in banners.BannersQuery(begin=self._begin, end=self._end):
            if d['kind'] != 'speaker':
                continue
            begin = d['begin']
            end = d['begin'] + timedelta(seconds=d['duration'])
            if begin >= text_begin and end <= text_end:
                return f"#{speaker}  - {d['content']}"
        return f"#{speaker}"

    def lookupTopic(self, timestamp):
        for d in banners.BannersQuery(begin=self._begin, end=self._end):
            if d['kind'] != 'topic':
                continue
            begin = d['begin']
            end = d['begin'] + timedelta(seconds=d['duration'])
            if timestamp >= begin and timestamp <= end:
                return d['content']
        return None
