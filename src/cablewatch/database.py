import duckdb
from cablewatch import config


def connect():
    conf = config.Config()
    path = f'{conf.DATABASE_PATH}'
    return duckdb.connect(path)
