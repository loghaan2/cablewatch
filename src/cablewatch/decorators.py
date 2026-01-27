import types
from functools import update_wrapper
from loguru import logger
from cablewatch import http, loghlp, arghlp


http_get = http.RouterDecorator('add_get')


class LogExceptionWrapper:
    def __init__(self, *, decorated, reraise=False, title=None, level='ERROR', logger=None):
        self._decorated = decorated
        self._reraise = reraise
        self._title = title
        self._level = level
        self._logger = logger
        update_wrapper(self, decorated)

    def __get__(self, instance, owner):
        bound = self._decorated
        if isinstance(self._decorated, (classmethod, staticmethod)):
            bound = self.__call__.__get__(instance, owner)
        elif instance is not None:
            bound = types.MethodType(self._decorated, instance)
        return self.__class__(decorated=bound, reraise=self._reraise, title=self._title, level=self._level, logger=self._logger)

    def __call__(self, *args, **kwargs):
        try:
            f = self._decorated
            return f(*args, **kwargs)
        except Exception:
            loghlp.log_exception(logger=self._logger, title=self._title, level=self._level)
            if self._reraise:
                raise


def log_exception(decorated=None, **kwargs):
    def inner(decorated):
        return LogExceptionWrapper(decorated=decorated, **kwargs)
    if decorated is not None:
        return inner(decorated)
    else:
        return inner


class ToolDecorator:
    def __init__(self):
        self._actions = {}
        self._extra_options = {}
        this = self
        class BaseTool:
            def __init__(self, args=None, **extra_options):
                self._args = args
                self._extra_options = extra_options
                self._ns = None
                self._tooldec = this
            def __call__(self):
                try:
                    tooldec = self._tooldec
                    p = arghlp.ArgumentParser(tool=self, tooldec=tooldec)
                    ns = p.parse_args(self._args, **self._extra_options)
                    self._ns = ns
                    f = tooldec.getActionCallable(ns.action)
                    f(self)
                finally:
                    logger.complete()
            @property
            def classname(self):
                return self.__class__.__name__
        self.BaseTool = BaseTool

    def getActionNames(self):
        return list(self._actions.keys())

    def getActionCallable(self, name):
        return self._actions[name]

    def getExtraOptions(self, name):
        try:
            return self._extra_options[name]
        except KeyError:
            return {}

    def action(self, *names, **extra_options):
        def inner(obj):
            for n in names:
                self._actions[n]=obj
                self._extra_options[n] = extra_options
            return obj
        return inner
