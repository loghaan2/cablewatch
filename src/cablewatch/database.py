import duckdb
from cablewatch import config


def connect(read_only=False):
    conf = config.Config()
    path = f'{conf.DATABASE_PATH}'
    return duckdb.connect(path, read_only=read_only)
