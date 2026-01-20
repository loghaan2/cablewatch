from datetime import datetime, time, timedelta
import re
import argparse


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *, actions=None, timeline_tool=None, speech_extractor=None, super_service=None):
        if actions is None:
            usage = '%(prog)s <options>'
        else:
            usage=f'%(prog)s <{"|".join(actions)}> <options>'
        super().__init__(usage=usage)
        self.__actions = actions
        if timeline_tool:
            self.add_argument('-s','--slice-index', dest='slice_index', default=0, type=int, help="set slice index")
            self.add_argument('--audio', dest='only', default=None, action='store_const', const='audio', help="only audio")
            self.add_argument('--video', dest='only', default=None, action='store_const', const='audio', help="only video")
        if speech_extractor:
            self.add_argument('-k', '--keep-bucket', dest='keep_bucket', default=speech_extractor.KEEP_BUCKET, action='store_true', help="keep files in buckets")
            self.add_argument('-l', '--local-copy', dest='local_copy', default=speech_extractor.LOCAL_COPY, action='store_true',  help="make a local copy .wav and .json files")
        if speech_extractor or timeline_tool:
            self.add_argument('-B', '--begin', dest='begin', default=None, help="begin")
            self.add_argument('-E', '--end', dest='end', default=None, help="end")
            self.add_argument('-D', '--day', dest='day', default=None, help="day")
            self.add_argument('-d','--duration', dest='duration', default="900s", help="set timeline duration")
        if super_service:
            self.add_argument('-n', '--no-record-planification', dest='record_planification', default=True, action='store_false', help="no record planification")
            self.add_argument('-H', '--halt', dest='recording_requested', default=True, action='store_false', help="start ingest in halt mode")

    def parseDate(self, s):
        for format in "%Y%m%d",:
            try:
                return datetime.strptime(s, format).date()
            except ValueError:
                continue
        raise ValueError

    def parseTime(self, s):
        for format in "%Hh%Mm%S", "%Hh%M", "%Hh":
            try:
                return datetime.strptime(s, format).time()
            except ValueError:
                continue
        raise ValueError

    def parseTimeDelta(self, s):
        for pattern in r"^(?P<seconds>\d+)s$",:
            m = re.match(pattern, s)
            if m:
                d = {'seconds': 0, 'minutes': 0, 'hours': 0}
                d.update(m.groupdict())
                for k,v in d.items():
                    d[k] = float(v)
                return timedelta(**d)
        raise ValueError

    def parse_args(self, args):
        prog = args[0]
        ns,args = self.parse_known_args(args[1:])
        ns.prog = prog
        ns.action = None
        ns.largs = []
        ns.rargs = []
        xargs = ns.largs
        if self.__actions is not None:
            if args[0] not in self.__actions:
                self.error(f'invalid action {args[0]!r}')
            ns.action = args[0]
        for a in args[1:]:
            if a == '--':
                xargs = ns.rargs
            else:
                xargs.append(a)
        if self.__actions is not None:
            if ns.action is None:
                self.error('no action secified')
        if 'day' in ns:
            if ns.day is not None:
                ns.day = datetime.strptime(ns.day, "%Y%m%d").date()
            else:
                ns.day = datetime.now().date()
        if 'begin' in ns:
            if ns.begin is not None:
                ns.begin = self.parseTime(ns.begin)
            else:
                ns.begin = time.min
            ns.begin = datetime.combine(ns.day, ns.begin)
        if 'end' in ns:
            if ns.end is not None:
                ns.end = self.parseTime(ns.end)
            else:
                ns.end = time.max
            ns.end = datetime.combine(ns.day, ns.end)
        if 'duration' in ns:
            ns.duration = self.parseTimeDelta(ns.duration)
        return ns
