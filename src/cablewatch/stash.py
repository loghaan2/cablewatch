import sys
import os
import time
import subprocess
import re
from rich import print as rich_print
from cablewatch import config
from cablewatch.decorators import ToolDecorator


def main():
    tool = StashTool(args=sys.argv, action='list')
    tool()


def system(cmd):
    conf = config.Config()
    rich_print(f'[cyan]{cmd}[/]')
    subprocess.run(
        cmd,
        cwd = conf.PROJECT_DIR,
        shell = True,
        check = True,
    )


tooldec = ToolDecorator()


class StashTool(tooldec.BaseTool):
    EXT = '.tar'
    ENTRY_NAME_PATTERN = r"^[A-Za-z0-9_.-]+$"

    def getSourceEntryNames(self):
        conf = config.Config()
        names = []
        for bn in os.listdir(conf.STASH_DIR):
            pth = os.path.join(conf.STASH_DIR, bn)
            if bn.startswith('.'):
                continue
            if os.path.isdir(pth):
                continue
            if not bn.endswith(self.EXT):
                continue
            names.append(bn[:-len(self.EXT)])
        names.sort()
        return names

    @tooldec.action('list')
    def list(self):
        for n in self.getSourceEntryNames():
            print(n)

    def ensureValidEntryName(self, name):
        if not re.fullmatch(self.ENTRY_NAME_PATTERN, name):
            raise AssertionError(f'{name!r} is not a valid entry name')

    def getDestinationEntryName(self):
        ns = self._ns
        if len(ns.largs) > 0:
            self.ensureValidEntryName(ns.largs[0])
            return ns.largs[0]
        else:
            return time.strftime("%Y%m%d_%Hh%Mm%S")

    def getSourceEntryName(self):
        names = self.getSourceEntryNames()
        ns = self._ns
        if len(ns.largs) > 0:
            if ns.largs[0] not in names:
                raise AssertionError(f'{ns.largs[0]!r} does not exist')
            return ns.largs[0]
        else:
            return names[-1]

    @tooldec.action('save')
    def save(self):
        conf = config.Config()
        name = self.getDestinationEntryName()
        cmd = f"tar cvf {conf.STASH_DIR}/{name}{self.EXT} --exclude='.*' data/ logs/"
        system(cmd)

    @tooldec.action('load')
    def load(self):
        conf = config.Config()
        name = self.getSourceEntryName()
        cmd = f"tar xvf {conf.STASH_DIR}/{name}{self.EXT}"
        system(cmd)
        return name

    @tooldec.action('push')
    def push(self):
        self.save()
        self.purge()

    @tooldec.action('pop')
    def pop(self):
        self.purge()
        name = self.load()
        self._remove(name)

    @tooldec.action('content')
    def content(self):
        conf = config.Config()
        name = self.getSourceEntryName()
        cmd = f"tar tf {conf.STASH_DIR}/{name}{self.EXT} |sort"
        system(cmd)

    @tooldec.action('purge')
    def purge(self):
        conf = config.Config()
        system(f"rm -f {conf.INGEST_DATADIR}/*.ts")
        system(f"rm -f {conf.INGEST_DATADIR}/*.ts.discont-after")
        system(f"rm -f {conf.INGEST_DATADIR}/timelines/*.json")
        system(f"rm -f {conf.INGEST_DATADIR}/timelines/*.json~")
        system(f"rm -f {conf.INGEST_DATADIR}/tmp/*.ts")
        system(f"rm -f {conf.INGEST_DATADIR}/tmp/output.m3u8")
        system(f"rm -f {conf.SPEECH_DATADIR}/*.wav")
        system(f"rm -f {conf.SPEECH_DATADIR}/*.json")
        system(f"rm -f {conf.SPEECH_DATADIR}/*.json~")
        system(f"rm -f {conf.BANNERS_DATADIR}/*.png")
        system(f"rm -f {conf.BANNERS_DATADIR}/*.json")
        system(f"rm -f {conf.BANNERS_DATADIR}/*.json~")
        system(f"rm -f {conf.PAPERS_DATADIR}/*")
        system(f"rm -f {conf.DATABASE_PATH}")
        system(f"rm -f {conf.LOGS_DIR}/*.log")

    def _remove(self, name):
        conf = config.Config()
        cmd = f"rm -f {conf.STASH_DIR}/{name}{self.EXT}"
        system(cmd)

    @tooldec.action('remove', 'rm')
    def remove(self):
        ns = self._ns
        for name in ns.largs:
            self._remove(name)

    @tooldec.action('clear')
    def clear(self):
        conf = config.Config()
        for name in self.getSourceEntryNames():
            cmd = f"rm -f {conf.STASH_DIR}/{name}{self.EXT}"
            system(cmd)
