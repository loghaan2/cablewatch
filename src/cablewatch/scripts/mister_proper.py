#!/usr/bin/env python3

import subprocess


def system(cmd):
    print(cmd)
    subprocess.run(cmd, shell=True, check=True)


def main():
    try:
        import _bootstrap_package # noqa: F401
    except ImportError:
        pass
    from cablewatch import config
    conf = config.Config()
    system(f"rm -f {conf.INGEST_DATADIR}/*.ts")
    system(f"rm -f {conf.INGEST_DATADIR}/*.ts.discont-after")
    system(f"rm -f {conf.INGEST_DATADIR}/timelines/*.json")
    system(f"rm -f {conf.INGEST_DATADIR}/tmp/*.ts")
    system(f"rm -f {conf.INGEST_DATADIR}/tmp/output.m3u8")
    system(f"rm -f {conf.DATABASE_PATH}")
    system(f"rm -f {conf.SPEECH_DATADIR}/*.wav")
    system(f"rm -f {conf.SPEECH_DATADIR}/*.json")
    system(f"rm -f {conf.LOGS_DIR}/*.log")
    system("cablewatch-speech cleanup-bucket")

if __name__ == '__main__':
    main()
