import os
import fnmatch
import time
import asyncio
import aiohttp
from aiohttp import web
from loguru import logger
from cablewatch import config, loghlp
from cablewatch.decorators import http_get


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
            if not fnmatch.fnmatch(bn, filter):
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
        archive_name = f'{time.strftime("%Y%m%d_%Hh%M")}_papers_{filter.encode().hex()}'
        resp = web.StreamResponse(
            headers = {
                "Content-Type": "application/zip",
                "Content-Disposition": f'attachment; filename="{archive_name}.zip"',
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
