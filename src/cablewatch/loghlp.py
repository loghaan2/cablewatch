import sys
import logging
import traceback
import re
import os
from datetime import datetime, timedelta, time
from loguru import logger as _logger
from strip_ansi import strip_ansi
from cablewatch import config


class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = _logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        _logger.opt(exception=record.exc_info).log(
            level, record.getMessage()
        )


class Filter:
    ESCAPED = "[ ] . - # $"
    NON_ESCAPED = ": _ < > @ abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789"
    ESCAPED = ESCAPED.replace(' ','')
    NON_ESCAPED = NON_ESCAPED.replace(' ','')

    @classmethod
    def translate(cls, pattern):
        res = ''
        for ch in pattern:
            if ch=='*':
                res += '.*'
            elif ch=='+':
                res += '.+'
            elif ch in cls.ESCAPED:
                res += '\\' + ch
            elif ch in cls.NON_ESCAPED:
                res += ch
            else:
                raise SyntaxError('invalid oregexp pattern: %r' % pattern)
        res = '^' + res + '$'
        return res

    def __init__(self, pattern):
        self._orig_pattern = pattern
        self._translated_pattern = self.translate(pattern)
        self._obj = re.compile(self._translated_pattern)

    def __call__(self, record):
        name = record['name'] + record['extra']['name']
        m = self._obj.match(name)
        if m:
            return True
        else:
            return False


class StdoutTee:
    def __init__(self):
        self._fobj = None
        self._rotate_dt = None
        self.rotate()
        sys.stdout = self

    def rotate(self):
        conf = config.Config()
        if self._fobj is not None:
            self._fobj.close()
        symlinkname = f"{conf.LOGS_DIR}/current.log"
        if os.path.exists(symlinkname):
            os.unlink(symlinkname)
        now = datetime.now()
        dt = datetime.combine(now.date(), time(6, 0))
        if now >= dt:
            dt += timedelta(days=1)
        self._rotate_dt = dt
        filename = f"{conf.LOGS_DIR}/{now.strftime('%Y%m%d_%Hh%Mm')}.log"
        self._fobj = open(filename, 'w')
        os.symlink(filename, symlinkname)

    def write(self, text):
        self._fobj.write(strip_ansi(text))
        sys.__stdout__.write(text)
        self._fobj.flush()
        sys.__stdout__.flush()
        now = datetime.now()
        if now >= self._rotate_dt:
            self.rotate()

    def flush(self):
        pass


def setup(level='INFO', fileoutput=False, filterpattern=None):
    logging.root.handlers = []
    logging.root.setLevel(getattr(logging, level))
    intercept_handler = InterceptHandler()
    for name in (
        "aiohttp",
        "aiohttp.access",
        "aiohttp.server",
        "aiohttp.web",
    ):
        log = logging.getLogger(name)
        log.handlers = [intercept_handler]
        log.propagate = False
    _logger.remove()
    _logger.configure(extra={"name": ""})
    format = "<green>{time:YYYYMMDD}_{time:HH}h{time:mm}m{time:ss}</green> <level>{level}</level> <light-cyan>{name}</light-cyan><cyan>{extra[name]}</cyan> {message}"
    if filterpattern is not None:
        filter = Filter(filterpattern)
    else:
        filter = None
    _logger.add(
        lambda msg: print(msg, end=""),
        level=level,
        colorize=True,
        format=format,
        filter=filter,
        enqueue=True,
    )
    if fileoutput:
        StdoutTee()


def format_exception(*, exc=None, triplet=None, with_tb=True, remove_eol=True):
    if triplet is None and exc is None:
        et, ev, tb = sys.exc_info()
    elif exc is not None:
        et, ev, tb = exc.__class__, exc, None
        with_tb=False
    else:
        et, ev, tb = triplet
    if with_tb:
        lines = traceback.format_exception(et, ev, tb)
    else:
        lines = traceback.format_exception_only(et, ev)
    if not remove_eol:
        return lines
    lines_out = []
    for ln in lines:
        lines_out += ln.split('\n')
    lines = lines_out
    lines_out = []
    for ln in lines:
        if ln=='':
            continue
        lines_out.append(ln)
    return lines_out


def log_exception(*, logger, level="ERROR", title=None, triplet=None, with_tb=True):
    lines = format_exception(triplet=triplet, with_tb=with_tb, remove_eol=True)
    log_lines(lines, logger=logger, level=level, title=title)


def log_lines(lines, *, logger=None, level="ERROR", title=None):
    if logger is None:
        logger = _logger
    ncols = 40
    for ln in lines + [title]:
        if ln is None:
            ln = ''
        ncols = max(ncols, len(ln) + 4)
    logger.log(level,'=' * ncols)
    if title:
        logger.log(level,title)
        logger.log(level,'-' * ncols)
    for ln in lines:
        logger.log(level,'  ' + ln)
    logger.log(level,'=' * ncols)
    logger.log(level,'')
