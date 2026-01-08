import pathlib
import re
import tomllib


class Config:
    _state = None

    WEB_LISTENADDR = '0.0.0.0'
    WEB_PORT = 8000
    WEB_ROOTDIR = '{PROJECT_DIR}/www'
    LOGS_DIR =  '{PROJECT_DIR}/logs'
    INGEST_DATADIR =  '{PROJECT_DIR}/data/ingest'
    INGEST_YOUTUBE_STREAM_URL = 'https://www.youtube.com/watch?v=Z-Nwo-ypKtM'
    PROJECT_DIR = f"{str(pathlib.Path(__file__).parent.parent.parent)}"
    YT_DLP_EXTRA_ARGS = ''

    def __init__(self):
        if self.__class__._state is not None:
            self.__dict__ = self._state
            return
        try:
            with open(f"{self.PROJECT_DIR}/cablewatch-local.toml", "rb") as f:
                d = tomllib.load(f)
                if 'config' in d:
                    for k,v in d['config'].items():
                        if self._is_conf_attr_name(k):
                            setattr(self,k,v)
        except FileNotFoundError:
            pass
        self.__class__._state = self.__dict__

    @staticmethod
    def _is_conf_attr_name(name):
        if (name.startswith('_')) or (name != name.upper()):
            return False
        else:
            return True

    def __getattribute__(self, name):
        if Config._is_conf_attr_name(name):
            return self._get_conf_attr(name)
        else:
            return super().__getattribute__(name)

    def _get_conf_attr(self, name, *, resolve_context=None):
        if resolve_context is None:
            resolve_context = [name]
        if len(resolve_context) > 8:
            raise RecursionError(f'Recursion error while resolving {" -> ".join(resolve_context)}')
        value = super().__getattribute__(name)
        if isinstance(value, str):
            d = {}
            for k in re.findall(r"\{([\w]+)\}", value):
                if Config._is_conf_attr_name(k):
                    d[k] = self._get_conf_attr(k, resolve_context=resolve_context + [k])
            return value.format(**d)
        else:
            return value

    def asDict(self):
        d = {}
        for k in dir(self):
            if Config._is_conf_attr_name(k):
                v = self._get_conf_attr(k)
                d[k] = v
        return d

    def __repr__(self):
        rval = f'<{self.__class__.__name__}\n'
        d = self.asDict()
        for k,v in d.items():
            rval += f'  {k}={v!r}\n'
        rval += '>\n'
        return rval
