from cablewatch import loghlp
from datetime import datetime, time, timedelta
import re
import argparse


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *, actions=None, default_action=None, ingest_tool=None, speech_tool=None, super_service=Nonee):
        if actions is None:
            usage = '%(prog)s <options>'
        else:
            usage=f'%(prog)s <{"|".join(actions)}> <options>'
        super().__init__(usage=usage)
        self.__actions = actions
        self.__default_action = default_action
        if ingest_tool:
            group = self.add_argument_group("Timeline tool options")
            group.add_argument('-s','--slice-index', dest='slice_index', default=0, type=int, help="set slice index")
            group.add_argument('--audio', dest='only', default=None, action='store_const', const='audio', help="only audio")
            group.add_argument('--video', dest='only', default=None, action='store_const', const='video', help="only video")
        if speech_tool:
            group = self.add_argument_group("Speech extractor tool options")
            group.add_argument('-k', '--keep-bucket', dest='keep_bucket', default=speech_tool.KEEP_BUCKET, action='store_true', help="keep files in buckets")
            group.add_argument('-c', '--local-copy', dest='local_copy', default=speech_tool.LOCAL_COPY, action='store_true',  help="make a local copy .wav and .json files")
            group.add_argument('-f', '--output-format', dest='output_format', default=None, help="output format")
        if speech_tool or ingest_tool:
            group = self.add_argument_group("Time range options")
            group.add_argument('-B', '--begin', dest='begin', default=None, help="begin")
            group.add_argument('-E', '--end', dest='end', default=None, help="end")
            group.add_argument('-D', '--day', dest='day', default=None, help="day")
            group.add_argument('-d','--duration', dest='duration', default=None, help="set timeline duration")
        if super_service:
            group = self.add_argument_group("Super service options")
            group.add_argument('-n', '--no-record-planification', dest='record_planification', default=True, action='store_false', help="no record planification")
            group.add_argument('-N', '--no-speech-planification', dest='speech_planification', default=True, action='store_false', help="no speech planification")
            group.add_argument('-H', '--halt', dest='recording_requested', default=True, action='store_false', help="start ingest in halt mode")
            log_level = 'INFO'
            log_fileoutput = True
        else:
            log_level = 'CRITICAL'
            log_fileoutput = False
        group = self.add_argument_group("Logging options")
        group.add_argument('-l', dest='log_level', default=log_level, help="set log level")
        if log_fileoutput:
            action='store_false'
        else:
            action='store_true'
        group.add_argument('-L', dest='log_fileoutput', default=log_fileoutput, action=action, help="toggle log file output")

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
            if len(args) > 0:
                ns.action = args.pop(0)
                if  ns.action not in self.__actions:
                    self.error(f'invalid action {ns.action!r}')
            if ns.action is None:
                if self.__default_action is None:
                    self.error('no action secified')
                else:
                    ns.action = self.__default_action
        for a in args:
            if a == '--':
                xargs = ns.rargs
            else:
                xargs.append(a)
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
            if ns.duration is not None:
                ns.end = ns.begin + self.parseTimeDelta(ns.duration)
        if 'begin' in ns and ('end' in ns):
            ns.duration = ns.end - ns.begin
        loghlp.setup(level=ns.log_level.upper(), fileoutput=ns.log_fileoutput)
        return ns
