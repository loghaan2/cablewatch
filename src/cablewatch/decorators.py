import types
from functools import update_wrapper
from cablewatch import http, loghlp


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
