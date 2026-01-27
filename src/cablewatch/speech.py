import subprocess
import re
import select
import sys
import os
import io
import math
from datetime import datetime, timedelta
import wave
import pathlib
import json
import collections
import difflib
import glob
from loguru import logger
from google.cloud import storage, speech_v2
from google.cloud.speech_v2.types import (
    BatchRecognizeRequest,
    BatchRecognizeFileMetadata,
    RecognitionConfig,
    RecognitionOutputConfig,
    GcsOutputConfig,
    RecognitionFeatures,
    SpeakerDiarizationConfig,
)
from rich.table import Table
from rich import print as rich_print
from rich.console import Console
from cablewatch import config, ingest
from cablewatch.decorators import ToolDecorator


def main():
    tool = SpeechTool(args=sys.argv, action='gold')
    tool()


def readline(fd):
    line = b''
    while True:
        ch = os.read(fd, 1)
        if len(ch) == 0:
            return ''
        if ch==b'\r' or ch==b'\n':
            return line.strip().decode()
        else:
            line += ch


DATETIME_FORMAT = "%Y%m%d_%Hh%Mm%S"


tooldec = ToolDecorator()

class SpeechTool(tooldec.BaseTool):
    LOCATION = 'eu'
    SV2_LANGUAGE = 'fr-FR'
    SV2_MODEL = 'chirp_3'
    SV2_MIN_SPEAKER = 1
    SV2_MAX_SPEAKER = 8
    TIMELINE_NAME = 'speech'
    OVERLAP_DURATION = 10
    WAV_SAMPLE_RATE = 16000
    WAV_SAMPLE_WIDTH = 2
    WAV_NUM_CHANNELS = 1 # mono
    WAV_HEADER_SIZE = 44
    WAV_CHUNK_SIZE = 256
    WAV_BASENAME_FORMAT = '{datetime}_{duration_ms}ms.wav'
    WAV_BASENAME_PATTERN = r'^(.+)_(.+)ms(\.wav)?$'
    WAV_MIN_NUM_FILES_TO_LAUNCH = 5
    KEEP_BUCKET = False
    LOCAL_COPY = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args,**kwargs)
        conf = config.Config()
        client_options = {"api_endpoint": f"{self.LOCATION}-speech.googleapis.com"}
        self._sv2_client = speech_v2.SpeechClient(client_options=client_options)
        self._sv2_recognizer = f"projects/{conf.GCP_PROJECT_ID}/locations/{self.LOCATION}/recognizers/_"
        self._sv2_config = RecognitionConfig(
            auto_decoding_config={},
            language_codes=[self.SV2_LANGUAGE],
            model=self.SV2_MODEL,
            features=RecognitionFeatures(
                diarization_config=SpeakerDiarizationConfig(
                    min_speaker_count=self.SV2_MIN_SPEAKER,
                    max_speaker_count=self.SV2_MAX_SPEAKER,
                ),
                enable_word_time_offsets=True,
            )
        )
        self._storage_client = storage.Client.from_service_account_json(conf.GCP_SERVICE_ACCOUNT)

    def secondsToNumSamples(self, seconds):
        if seconds == math.inf:
            return math.inf
        return int(seconds * self.WAV_SAMPLE_RATE) * self.WAV_SAMPLE_WIDTH

    def numSamplesToSeconds(self, nsamples):
        if nsamples == math.inf:
            return math.inf
        return nsamples / (self.WAV_SAMPLE_RATE * self.WAV_SAMPLE_WIDTH)

    @tooldec.action('init', begin='fseg.begin')
    def init(self):
        ns = self._ns
        tl = ingest.IngestTimeLine(self.TIMELINE_NAME, begin=ns.begin, duration=ns.duration)
        tl.save()
        logger.info(f'timeline created: {tl.name!r} begin={tl.begin.strftime(DATETIME_FORMAT)!r} duration={tl.duration.total_seconds()!r}')

    @tooldec.action('upload')
    def convertAndUpload(self):
        try:
            tl = ingest.IngestTimeLine.load(self.TIMELINE_NAME)
        except KeyError:
            logger.warning(f'cannot open timeline {self.TIMELINE_NAME!r} => nothing to do')
            return
        if not tl.isReady():
            logger.warning(f"timeline {self.TIMELINE_NAME!r} currently not ready => nothing to do")
            return
        ns = self._ns
        logger.info(f'timeline before: {tl.name!r} begin={tl.begin.strftime(DATETIME_FORMAT)!r} duration={tl.duration.total_seconds()!r}')
        slices = tl.slices()
        if len(slices) == 0:
            logger.warning("currently no slices, nothing to do")
            return
        try:
            for slice in slices:
                basename, wav_frames = self.makeWavFromSlice(slice)
                self.uploadWavFile(basename, wav_frames)
        except:
            raise
        finally:
            if not ns.stay:
                begin = tl.begin + timedelta(seconds=tl.effective_duration.total_seconds()-self.OVERLAP_DURATION)
                tl.init(tl.name, begin=begin, duration=tl.duration)
                tl.save()
                logger.info(f'timeline after: {tl.name!r} begin={tl.begin.strftime(DATETIME_FORMAT)!r} duration={tl.duration.total_seconds()!r}')

    def makeWavFromSlice(self, slice):
        inputs_and_filter = slice.generateConcatCommand(only='audio')
        cmd = ['ffmpeg'] + inputs_and_filter
        cmd += ['-vn', '-ac', f'{self.WAV_NUM_CHANNELS}', '-ar', f'{self.WAV_SAMPLE_RATE}', '-f', 'wav', 'pipe:1']
        logger.info(f'run {" ".join(cmd)!r}')
        proc = subprocess.Popen(
            cmd,
            shell = False,
            stdin = subprocess.DEVNULL,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
        )
        poller = select.poll()
        active_fds = {proc.stdout.fileno(), proc.stderr.fileno()}
        for fd in active_fds:
            poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
        wav_frames =b''
        wav_header = None
        while len(active_fds) > 0:
            for fd, ev in poller.poll():
                if ev & select.POLLERR:
                    raise AssertionError
                elif ev & (select.POLLIN | select.POLLHUP):
                    if fd == proc.stderr.fileno(): # ffmpeg log output
                        ln = readline(fd)
                        if len(ln) == 0:
                            logger.info("ffmpeg log output EOF")
                            poller.unregister(fd)
                            active_fds.remove(fd)
                            break
                        logger.bind(name='[ffmpeg]').debug(ln)
                        if ln.endswith('\n'):
                            ln = ln[:-1]
                    else: # ffmpeg wav output
                        if wav_header is None:
                            wav_header = os.read(fd,self.WAV_HEADER_SIZE)
                        else:
                            wav_chunk = os.read(fd, self.WAV_CHUNK_SIZE)
                            if len(wav_chunk) == 0:
                                logger.info("ffmpeg wav output EOF")
                                poller.unregister(fd)
                                active_fds.remove(fd)
                                break
                            wav_frames += wav_chunk
        slice_duration = slice.effective_duration.total_seconds()
        wav_duration = self.numSamplesToSeconds(len(wav_frames))
        duration_ms = int(wav_duration * 1000)
        basename = self.WAV_BASENAME_FORMAT.format(datetime=slice.begin.strftime(DATETIME_FORMAT), duration_ms=duration_ms)
        size_m = (len(wav_frames) + self.WAV_HEADER_SIZE) / (1024*1024)
        logger.info(f'wav file prepared: basename={basename!r} slice_duration={slice_duration:.2f}s wav_duration={wav_duration:.2f}s size={size_m:.2f}M')
        return basename, wav_frames

    def uploadWavFile(self, basename, wav_frames):
        ns = self._ns
        buf = io.BytesIO()
        conf = config.Config()
        with wave.open(buf, 'wb') as f:
            f.setnchannels(self.WAV_NUM_CHANNELS)
            f.setsampwidth(self.WAV_SAMPLE_WIDTH)
            f.setframerate(self.WAV_SAMPLE_RATE)
            f.writeframes(wav_frames)
        if ns.local_copy:
            buf.seek(0)
            with open(f'{conf.SPEECH_DATADIR}/{basename}', 'wb') as f:
                f.write(buf.read())
            logger.info(f"copy {basename!r} locally")
        buf.seek(0)
        client = self._storage_client
        bucket = client.bucket(conf.GCP_BUCKET_NAME)
        blob = bucket.blob(f"speech-extractor/uploaded/{basename}")
        blob.upload_from_file(buf, content_type="audio/wav")
        logger.info(f"{basename!r} uploaded")

    @tooldec.action('launch')
    def launchTranscriptions(self):
        conf = config.Config()
        client = self._storage_client
        bucket = client.bucket(conf.GCP_BUCKET_NAME)
        launched = set()
        for blob in bucket.list_blobs(prefix="speech-extractor/launched/"):
            if blob.name.endswith('/'):
                continue
            launched.add(pathlib.Path(blob.name).stem)
        files = []
        for blob in bucket.list_blobs(prefix="speech-extractor/uploaded/"):
            if blob.name.endswith('/'):
                continue
            pth = pathlib.Path(blob.name)
            if pth.stem in launched:
                continue
            files.append(BatchRecognizeFileMetadata(uri=f"gs://{conf.GCP_BUCKET_NAME}/speech-extractor/uploaded/{pth.name}"))
        if len(files) < self.WAV_MIN_NUM_FILES_TO_LAUNCH:
            logger.warning(f"no enough wav files ({self.WAV_MIN_NUM_FILES_TO_LAUNCH} needed) to start launching")
            return
        output_config = RecognitionOutputConfig(
            gcs_output_config=GcsOutputConfig(
                uri=f"gs://{conf.GCP_BUCKET_NAME}/speech-extractor/results/"
            )
        )
        request = BatchRecognizeRequest(
            recognizer=self._sv2_recognizer,
            config=self._sv2_config,
            files=files,
            recognition_output_config=output_config,
        )
        client = self._sv2_client
        operation = client.batch_recognize(request=request)
        logger.info("The following wav files will be processed under the operation")
        logger.info(f" {operation.operation.name!r}:")
        buf = io.BytesIO(operation.operation.name.encode())
        for f in files:
            pth = pathlib.Path(f.uri)
            blob = bucket.blob(f"speech-extractor/launched/{pth.stem}.txt")
            buf.seek(0)
            blob.upload_from_file(buf, content_type="text/plain")
            logger.info(f"  - {f.uri}")

    @tooldec.action('fetch')
    def fetchResults(self):
        ns = self._ns
        conf = config.Config()
        client = self._storage_client
        bucket = client.bucket(conf.GCP_BUCKET_NAME)
        results = {}
        for blob in bucket.list_blobs(prefix="speech-extractor/results/"):
            if blob.name.endswith('/'):
                continue
            pth = pathlib.Path(blob.name)
            m = re.match(r'^(.+)_transcript_(.+)\.json$', pth.name)
            if not m:
                continue
            results[m.group(1)] = json.loads(blob.download_as_text())
            if not ns.keep_bucket:
                logger.info(f"delete blob {blob.name!r}")
                blob.delete()
            with open(f'{conf.SPEECH_DATADIR}/{m.group(1)}.json', 'w') as f:
                f.write(json.dumps(results[m.group(1)], indent=4))
        for folder in 'uploaded', 'launched':
            for blob in bucket.list_blobs(prefix=f"speech-extractor/{folder}/"):
                if blob.name.endswith('/'):
                    continue
                pth = pathlib.Path(blob.name)
                if pth.stem not in results:
                    continue
                if not ns.keep_bucket:
                    logger.info(f"delete blob {blob.name!r}")
                    blob.delete()

    @tooldec.action('list-bucket', 'lsb')
    def listBucket(self):
        table = Table()
        table.add_column("NAME")
        table.add_column("SIZE", justify="right")
        table.add_column("CONTENT")
        client = self._storage_client
        conf = config.Config()
        bucket = client.bucket(conf.GCP_BUCKET_NAME)
        prefix = 'speech-extractor/'
        for blob in bucket.list_blobs(prefix=prefix):
            if blob.name.endswith('/'):
                content = ''
                size = ''
            elif blob.name.startswith(f'{prefix}launched/') and blob.name.endswith('.txt'):
                content = blob.download_as_text()
                size = f'{blob.size/1024:.2f}K'
            else:
                content = '?'
                size = f'{blob.size/(1024*1024):.2f}M'
            table.add_row(blob.name, size, content)
        rich_print(table)

    @tooldec.action('cleanup-bucket', 'clb')
    def cleanupBucket(self):
        client = self._storage_client
        conf = config.Config()
        bucket = client.bucket(conf.GCP_BUCKET_NAME)
        prefix = 'speech-extractor/'
        for blob in bucket.list_blobs(prefix=prefix):
            if blob.name == prefix:
                continue
            elif blob.name.endswith('/'):
                continue
            logger.warning(f'delete {blob.name}')
            blob.delete()

    @tooldec.action('bronze', 'silver', 'gold')
    def view(self):
        console = Console(force_terminal=True)
        ns = self._ns
        if ns.output_format=='text':
            printer = SpeechTextPrinter(console)
        else:
            printer = console
        for d in SpeechQuery(begin=ns.begin, end=ns.end, layer=ns.action):
            if 'timestamp' in d:
                d['timestamp'] = d['timestamp'].strftime(DATETIME_FORMAT)
            if 'pos' in d:
                d['pos'] = f"{d['pos']:04d}"
            printer.print(d)


class SpeechTextPrinter:
    SPEAKER_COLORS = [
        "purple", "green", "yellow", "red", "blue", "cyan"
    ]
    STAMP_COLOR = 'white'
    def __init__(self, console):
        self._console = console
        self._speaker_colors = {}
        self._next_speaker_color_index = 0
        self._count = 0
        self._last_speaker = None

    def print(self, d):
        console = self._console
        speaker = d['speaker']
        kwargs = dict(end="", highlight=False)
        try:
            speaker_color = self._speaker_colors[speaker]
        except KeyError:
            speaker_color = self.SPEAKER_COLORS[self._next_speaker_color_index]
            self._speaker_colors[speaker] = speaker_color
            self._next_speaker_color_index = (self._next_speaker_color_index + 1) % len(self.SPEAKER_COLORS)
        if speaker != self._last_speaker:
            console.print(f'[{self.STAMP_COLOR}]<speaker:{speaker}>[/] ', **kwargs)
            self._count = 31
        if self._count > 30:
            console.print(f'[{self.STAMP_COLOR}]<{d["timestamp"][9:]}>[/] ', **kwargs)
            self._count = 0
        console.print(f'[{speaker_color}]{d["word"]}[/{speaker_color}] ', **kwargs)
        self._count += 1
        self._last_speaker = speaker


def find_longest_common_sublist_fuzzy(a, b, threshold=0.8):
    max_len = 0
    start_a = start_b = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 1
            while (i+k) <= len(a) and (j+k) <= len(b):
                s1 = a[i+k-1]
                s2 = b[j+k-1]
                ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
                if ratio < threshold:
                    break
                if k > max_len:
                    max_len = k
                    start_a = i
                    start_b = j
                k += 1
    return start_a, start_b, max_len


class SpeechQuery:
    WINDOW_SIZE = 100
    MIN_OVERLAP_SIZE = int(WINDOW_SIZE * 0.1)

    def __init__(self, *, begin, end, last=None, layer="gold", logger=None):
        if (begin is None) or (end is None):
            raise AssertionError
        conf = config.Config()
        self._begin = begin
        self._end = end
        self._logger = logger
        self._layer = layer
        self._last = last
        all_sequences_filenames = glob.glob(f"{conf.SPEECH_DATADIR}/*.json")
        all_sequences_filenames.sort()
        sequences = {}
        for fn in all_sequences_filenames:
            seq = SpeechSequence.fromFileName(fn)
            sequences[seq.begin] = seq
        self._sequences = sequences
        self._basenames = {}

    def inTimeRange(self, d):
        if d['timestamp'] >= self._begin and d['timestamp'] <= self._end:
            return True
        else:
            return False

    def __iter__(self):
        f = getattr(self, self._layer)
        yield from f()
        if self._last is not None:
            yield self._last

    def _raw(self):
        for seq in self._sequences.values():
            for x in seq.data['results'][0]['alternatives'][0]['words']:
                yield seq,x

    def bronze(self):
        previous_speaker = None
        previous_offset = None
        fileids = {}
        next_fileid = 0
        pos = 0
        self._basenames.clear()
        for seq, x in self._raw():
            if ('startOffset' in x) and ('endOffset' in x):
                offset = (float(x['startOffset'][:-1]) + float(x['endOffset'][:-1])) / 2
            elif 'endOffset' in x:
                offset = float(x['endOffset'][:-1])
            elif 'startOffset' in x:
                offset = float(x['startOffset'][:-1])
            else:
                offset = previous_offset
            if offset >= seq.duration.total_seconds():
                offset = previous_offset
            if 'speakerLabel' not in x:
                speaker = previous_speaker
            else:
                speaker = int(x['speakerLabel'])
            try:
                fileid = fileids[seq.basename]
            except KeyError:
                fileid = next_fileid
                next_fileid += 1
                fileids[seq.basename] = fileid
                self._basenames[fileid] = seq.basename
                pos = 0
            d = {}
            d['fileid'] = fileid
            d['timestamp'] = seq.begin + timedelta(seconds=offset)
            d['speaker'] = speaker
            d['pos'] = pos
            d['word'] = x['word']
            if self.inTimeRange(d):
                yield d
            previous_offset = offset
            previous_speaker = speaker
            pos += 1

    def silver(self):
        window = []
        for d in self.bronze():
            window.append(d)
            if len(window) == self.WINDOW_SIZE + 1:
                d2 = window.pop(0)
                yield d2
            if d['pos'] == (self.WINDOW_SIZE/2) - 1:
                window = self._silverInner(window)
                for d in window:
                    yield d
                window.clear()

    def _silverInner(self, window):
        words = collections.defaultdict(list)
        speakers = collections.defaultdict(list)
        for d in window:
            k = d['fileid']
            words[k].append(d['word'])
            speakers[k].append(d['speaker'])
        keys = list(sorted(words.keys()))
        if len(keys) != 2:
            return window
        bn0 = self._basenames[keys[0]]
        bn1 = self._basenames[keys[1]]
        words0 = words[keys[0]]
        words1 = words[keys[1]]
        start0, start1, overlap_size = find_longest_common_sublist_fuzzy(words0, words1)
        common_words = words0[start0:start0+overlap_size]
        def _(list_): return ' '.join(list_)
        if overlap_size >= self.MIN_OVERLAP_SIZE:
            level = 'INFO'
        else:
            level = 'ERROR'
        logger.log(level, '')
        logger.log(level, f'{"="*100}')
        logger.log(level, f'{bn0} -> {bn1}')
        logger.log(level, f'{'' if level=="INFO" else 'no '}overlap detected')
        logger.log(level, f'words0:  {_(words0)!r}')
        logger.log(level, f'words1:  {_(words1)!r}')
        logger.log(level, f'start0={start0} start1={start1}')
        logger.log(level, f'overlap_size={overlap_size} min_overlap_size={self.MIN_OVERLAP_SIZE}')
        logger.log(level, f'common_words:  {_(common_words)!r}')
        logger.log(level, f'{"="*100}')
        if overlap_size < self.MIN_OVERLAP_SIZE:
            return window
        new_window = []
        for i,d in enumerate(window):
            if d['fileid']==keys[0]:
                if i < start0:
                    new_window.append(d)
            else:
                if i >= (start1 + self.MIN_OVERLAP_SIZE/2):
                    new_window.append(d)
        return new_window

    def gold(self):
        for d in self.silver():
            d2 = {**d}
            d2['speaker'] = 100 * d['fileid']  +  d['speaker']
            del d2['fileid']
            del d2['pos']
            yield d2


class SpeechSequence:
    JSON_BASENAME_PATTERN = SpeechTool.WAV_BASENAME_PATTERN.replace(r'\.wav',r'\.json')

    @staticmethod
    def fromFileName(filename):
        basename = os.path.basename(filename)
        m = re.match(SpeechSequence.JSON_BASENAME_PATTERN, basename)
        if not m:
            raise AssertionError(f'cannot parse result filename: {basename!r}')
        begin = datetime.strptime(m.group(1), DATETIME_FORMAT)
        duration = timedelta(seconds=float(m.group(2))/1000)
        return SpeechSequence(filename=filename, basename=basename, begin=begin, duration=duration)

    def __init__(self, *,filename, basename, begin, duration):
        self.filename = filename
        self.basename = basename
        self.begin = begin
        self.duration = duration
        with open(self.filename, 'r') as f:
            self.data = json.loads(f.read())

    @property
    def end(self):
        return self.begin + self.duration

    def __repr__(self):
        s = f'<{self.__class__.__name__} at {hex(id(self))}'
        for k,v in self.__dict__.items():
            if k=='data':
                continue
            else:
                s += f' {k}={v!r}'
        s += '>'
        return s
