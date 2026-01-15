import duckdb
from loguru import logger
from cablewatch import config


def connect(read_only=False):
    conf = config.Config()
    path = f'{conf.DATABASE_PATH}'
    logger.info(f"open database read_only={read_only}")
    return duckdb.connect(path, read_only=read_only)
