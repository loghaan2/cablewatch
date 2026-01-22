import logging
import base64
from aiohttp import web
from loguru import logger
from cablewatch import config, user


class RouterDecorator:
    ATTRIBUTE_NAME = '__cablewatch_http_routes'

    def __init__(self, method):
        self._method = method

    def __call__(self, path, **kwargs):
        def inner(handler):
            if not hasattr(handler, self.ATTRIBUTE_NAME):
                setattr(handler, self.ATTRIBUTE_NAME, [])
            routes = getattr(handler, self.ATTRIBUTE_NAME)
            routes += [(self._method, path, kwargs)]
            return handler
        return inner


@web.middleware
async def perform_basic_authentification(request, handler):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Basic "):
        raise web.HTTPUnauthorized(
            headers={"WWW-Authenticate": 'Basic realm="Restricted"'}
        )
    encoded = auth.split(" ", 1)[1]
    decoded = base64.b64decode(encoded).decode()
    username, password = decoded.split(":", 1)
    u = user.User(username)
    if not u.verifyPassword(password):
        raise web.HTTPUnauthorized(
            headers={"WWW-Authenticate": 'Basic realm="Restricted"'}
        )
    request["user"] = u
    return await handler(request)


class HTTPService:
    def __init__(self):
        self._app = web.Application(middlewares=[perform_basic_authentification])
        conf = config.Config()
        self._app.router.add_static(
            prefix="/",
            path=conf.ROOT_WEBDIR,
            show_index=True
        )
        self._app.router.add_static(
            prefix="/docs",
            path=f"{conf.DOCS_WEBDIR}",
            show_index=True
        )

    def addDecoratedRoutes(self, instance):
        router = self._app.router
        for name in dir(instance):
            handler = getattr(instance, name)
            try:
                routes = getattr(handler, RouterDecorator.ATTRIBUTE_NAME)
            except AttributeError:
                continue
            for method, path, kwargs in routes:
                f = getattr(router, method)
                f(path, handler, **kwargs)

    async def start(self):
        logger.info("starting web service")
        conf = config.Config()
        runner = web.AppRunner(self._app, access_log=logging.getLogger("aiohttp.access"))
        await runner.setup()
        site = web.TCPSite(runner, conf.WEB_LISTENADDR, conf.WEB_PORT)
        await site.start()
        self._runner = runner
        logger.info("web service started")

    async def stop(self):
        logger.info("stopping web service !")
        await self._runner.cleanup()
        logger.info("web service stopped !")
