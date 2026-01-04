import logging
from loguru import logger
from cablewatch import config


class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        logger.opt(exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup():
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

    logger.remove()
    logger.configure(extra={"name": ""})

    format = "<green>{time:HH:mm:ss}</green> <level>{level}</level> <light-cyan>{name}</light-cyan><cyan>{extra[name]}</cyan> {message}"

    logger.add(
        lambda msg: print(msg, end=""),
        level="INFO",
        colorize=True,
        format=format,
    )

    logger.add(
        f"{conf.LOGS_DIR}/ingest_{{time:YYYY-MM-DD}}_{{time:HH}}h{{time:mm}}.log",
        rotation="06:00",
        retention="100 days",
        level="INFO",
        colorize=False,
        format=format,
    )
