import sys
import logging
import traceback
from loguru import logger as _logger
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


def setup(fileoutput=False):
    conf = config.Config()

    logging.root.handlers = []
    logging.root.setLevel(logging.INFO)

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

    _logger.add(
        lambda msg: print(msg, end=""),
        level="INFO",
        colorize=True,
        format=format,
    )

    if fileoutput:
        _logger.add(
            f"{conf.LOGS_DIR}/{{time:YYYYMMDD}}_{{time:HH}}h{{time:mm}}.log",
            rotation="06:00",
            retention="100 days",
            level="INFO",
            colorize=False,
            format=format,
            enqueue=True,
        )


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
