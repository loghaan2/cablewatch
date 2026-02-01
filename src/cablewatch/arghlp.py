import re
import argparse
from datetime import datetime, timedelta, time
from loguru import logger
from rich import print as rich_print
from cablewatch import loghlp


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *,
            tooldec=None,
            tool=None,
            classname=None,
        ):
        if tooldec is None:
            usage = '%(prog)s <options>'
        else:
            usage=f'%(prog)s <{"|".join(tooldec.getActionNames())}> <options>'
        super().__init__(usage=usage)
        self._tooldec = tooldec
        self._tool = tool
        if tool is not None:
            classname_ = tool.classname
        else:
            classname_ = classname
        if classname_ == 'IngestTool':
            group = self.add_argument_group("Ingest tool options")
            group.add_argument('-s','--slice-index', dest='slice_index', default=0, type=int, help="set slice index")
            group.add_argument('--audio', dest='only', default=None, action='store_const', const='audio', help="only audio")
            group.add_argument('--video', dest='only', default=None, action='store_const', const='video', help="only video")
        if classname_ == 'SpeechTool':
            group = self.add_argument_group("Speech tool options")
            group.add_argument('-k', '--keep-bucket', dest='keep_bucket', default=tool.KEEP_BUCKET, action='store_true', help="keep files in buckets")
            group.add_argument('-f', '--output-format', dest='output_format', default=None, help="output format")
            group.add_argument('-l', '--local-copy', dest='local_copy', default=tool.LOCAL_COPY, action='store_true',  help="make a local copy of .wav and .json files")
        if classname_ == 'BannersTool':
            group = self.add_argument_group("Banners tool options")
            group.add_argument('-l', '--local-copy', dest='local_copy', default=tool.LOCAL_COPY, action='store_true',  help="make a local copy of .png files")
        if classname_ == 'SpeechTool' or classname_ == 'BannersTool':
            group = self.add_argument_group("Banners/Speech tool options")
            group.add_argument('-S', '--stay', dest='stay', default=False, action='store_true')
        if classname_ == 'PapersTool':
            group = self.add_argument_group("Papers tools options")
        if classname_ == 'IngestTool' or classname_ == 'SpeechTool' or classname_ == 'BannersTool' or classname_ == 'PapersTool':
            group = self.add_argument_group("Time options")
            group.add_argument('-Tb', dest='begin',    default=None, help="begin")
            group.add_argument('-Te', dest='end',      default=None, help="end")
            group.add_argument('-Td', dest='duration', default=None, help="duration")
        if classname_ == 'SuperService':
            group = self.add_argument_group("Super service options")
            group.add_argument('-Ih',  dest='ingest_record',         default=True,  action='store_false',  help="start ingest in halt mode")
            group.add_argument('-Inp', dest='ingest_planification',  default=True,  action='store_false', help="no ingest planification")
            group.add_argument('-Sni', dest='speech_init',           default=True,  action='store_false', help="no speech init")
            group.add_argument('-Snp', dest='speech_planification',  default=True,  action='store_false', help="no speech planification")
            group.add_argument('-Bni', dest='banners_init',          default=True,  action='store_false', help="no banners init")
            group.add_argument('-Bnp', dest='banners_planification', default=True,  action='store_false', help="no banners planification")
            group.add_argument('--http-only', dest='http_only',      default=False,  action='store_true',  help="http only")
            group.add_argument('-Td',  dest='duration',              default=None,  help="timeline duration")
            log_fileoutput = True
        else:
            log_fileoutput = False
        group = self.add_argument_group("Logging options")
        for log_level in 'debug', 'info', 'warning', 'error', 'critical':
            group.add_argument(f'-L{log_level}', dest='log_level', default='INFO', action='store_const', const=log_level, help=f"set log level {log_level}")
        if log_fileoutput:
            action='store_false'
        else:
            action='store_true'
        group.add_argument('-Lo', dest='log_fileoutput', default=log_fileoutput, action=action, help="toggle log file output")
        group.add_argument('-Lf', dest='log_filterpattern', default=None, help="set log filter pattern")
        group = self.add_argument_group("Debug options")
        group.add_argument('-Dns',  dest='trace_ns', default=False, action='store_true', help="log filter")
        group.add_argument('-Dlogs',  dest='check_logs', default=False, action='store_true', help="check logs")

    def parseDateTimeWithDelta(self, s):
        idx_plus = s.find('+')
        idx_minus = s.find('-')
        if (idx_plus < 0) and (idx_minus < 0):
            return self.parseDateTime(s)
        elif (idx_plus >= 0) and (idx_minus >= 0):
            raise ValueError
        if idx_plus >= 0:
            idx = idx_plus
        else:
            idx = idx_minus
        dt = self.parseDateTime(s[:idx])
        delta = self.parseDelta(s[idx+1:])
        if idx_plus >= 0:
            return dt + delta
        else:
            return dt - delta

    def parseDateTime(self, s):
        today = datetime.combine(datetime.now().date(), time.min)
        from cablewatch import ingest
        tl = ingest.IngestTimeLine.load('.all')
        if s=='now':
            return datetime.now()
        elif s=='today':
            return today
        elif s=='yesterday':
            return today - timedelta(days=1)
        elif s=='begin':
            return tl.begin
        elif s=='end':
            return tl.end
        elif s=='fseg.begin':
            return tl.first_segment.begin
        elif s=='fseg.end':
            return tl.first_segment.end
        elif s=='lseg.begin':
            return tl.last_segment.begin
        elif s=='lseg.end':
            return tl.last_segment.end
        for format in "%Y%m%d_%Hh%Mm%S", "%Y%m%d_%Hh%M", "%Y%m%d_%Hh", "%Y%m%d", "%Hh%Mm%S", "%Hh%M", "%Hh":
            try:
                dt = datetime.strptime(s, format)
                if '%Y' not in format:
                    dt = datetime.combine(datetime.now().date(), dt.time())
                return dt
            except ValueError:
                continue
        raise ValueError

    def parseDelta(self, s):
        from cablewatch import ingest
        tl = ingest.IngestTimeLine.load('.all')
        if s=='duration':
            return tl.duration
        for pattern in r"^(?P<seconds>[0-9.]+)s$", r"^(?P<minutes>[0-9.]+)mn$", r"^(?P<hours>[0-9.]+)h$":
            m = re.match(pattern, s)
            if m:
                d = {'seconds': 0, 'minutes': 0, 'hours': 0}
                d.update(m.groupdict())
                for k,v in d.items():
                    d[k] = float(v)
                return timedelta(**d)
        raise ValueError

    def parse_args(self, args, *, action=None, **extra_options):
        if args is None:
            ns,args = self.parse_known_args([])
        else:
            ns,args = self.parse_known_args(args[1:])
        ns.action = action
        ns.largs = []
        ns.rargs = []
        xargs = ns.largs
        error = None
        tooldec = self._tooldec
        if tooldec is not None:
            if len(args) > 0:
                ns.action = args.pop(0)
            if ns.action not in tooldec.getActionNames():
                error = f'invalid action {ns.action!r}'
        for a in args:
            if xargs == ns.largs and a.startswith('-'):
                error = f'invalid option {a!r}'
            elif a == '--':
                xargs = ns.rargs
            else:
                xargs.append(a)
        def has_opt(k):
            if k in ns:
                if getattr(ns, k) is not None:
                    return True
            return False
        extra_options_ = {}
        if (tooldec is not None) and (ns.action is not None):
            extra_options_.update(tooldec.getExtraOptions(ns.action))
        extra_options_.update(extra_options)
        for k,v in extra_options_.items():
            if not has_opt(k):
                setattr(ns,k,v)
        if has_opt('begin') and has_opt('end') and has_opt('duration'):
            error = 'cannot mix begin, end and duration options'
        if has_opt('begin'):
            ns.begin = self.parseDateTimeWithDelta(ns.begin)
        if has_opt('end'):
            ns.end = self.parseDateTimeWithDelta(ns.end)
        if has_opt('duration'):
            ns.duration = self.parseDelta(ns.duration)
        if has_opt('begin') and has_opt('duration'):
            ns.end = ns.begin + ns.duration
        if has_opt('end') and has_opt('duration'):
            ns.begin = ns.end - ns.duration
        if has_opt('begin') and has_opt('end'):
            ns.duration = ns.end - ns.begin
        loghlp.setup(level=ns.log_level.upper(), fileoutput=ns.log_fileoutput, filterpattern=ns.log_filterpattern)
        if ns.trace_ns:
            rich_print(ns)
        if ns.check_logs:
            for lvl in 'debug', 'info', 'warning', 'error', 'critical':
                logger.bind(name=f'[{lvl[::-1]}]').log(lvl.upper(), f'{lvl}')
        if has_opt('http_only'):
            if ns.http_only:
                for opt in 'ingest_record', 'ingest_planification', 'speech_init', 'speech_planification', 'banners_init', 'banners_planification':
                    setattr(ns, opt, False)
        if error is not None:
            self.error(error)
        return ns
