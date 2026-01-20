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
import argparse
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
from cablewatch import config, ingest, loghlp, arghlp


def main():
    loghlp.setup()
    extractor = SpeechExtractor(sys.argv)
    extractor()


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


SETOOL_ACTIONS = {}


def SEtool_action(*names):
    def inner(obj):
        for n in names:
            SETOOL_ACTIONS[n]=obj
        return obj
    return inner


DATETIME_FORMAT = "%Y%m%d_%Hh%Mm%S"


class SpeechExtractor:
    LOCATION = 'eu'
    SV2_LANGUAGE = 'fr-FR'
    SV2_MODEL = 'chirp_3'
    SV2_MIN_SPEAKER = 1
    SV2_MAX_SPEAKER = 8
    TIMELINE_NAME = 'speech-extractor'
    TIMELINE_DURATION = 120
    OVERLAP_DURATION = 10
    WAV_SAMPLE_RATE = 16000
    WAV_SAMPLE_WIDTH = 2
    WAV_NUM_CHANNELS = 1 # mono
    WAV_HEADER_SIZE = 44
    WAV_CHUNK_SIZE = 256
    WAV_BASENAME_FORMAT = '{datetime}_{duration_ms}ms.wav'
    WAV_BASENAME_PATTERN = r'^(.+)_(.+)ms(\.wav)?$'
    KEEP_BUCKET = False
    LOCAL_COPY = False

    def __init__(self, args=None, action=None, local_copy=LOCAL_COPY, keep_bucket=KEEP_BUCKET):
        if args is None:
            self._ns = argparse.Namespace(action=action, local_copy=local_copy, keep_bucket=keep_bucket)
            self._argparser = None
        else:
            p = arghlp.ArgumentParser(speech_extractor=self, actions=SETOOL_ACTIONS.keys())
            self._ns = p.parse_args(args)
            self._argparser = p
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

    def __call__(self):
        ns = self._ns
        f = SETOOL_ACTIONS[ns.action]
        f(self)

    def secondsToNumSamples(self, seconds):
        if seconds == math.inf:
            return math.inf
        return int(seconds * self.WAV_SAMPLE_RATE) * self.WAV_SAMPLE_WIDTH

    def numSamplesToSeconds(self, nsamples):
        if nsamples == math.inf:
            return math.inf
        return nsamples / (self.WAV_SAMPLE_RATE * self.WAV_SAMPLE_WIDTH)

    @SEtool_action('init-timeline', 'init')
    def initTimeline(self):
        begin = datetime.now() - timedelta(seconds=35)
        tl = ingest.IngestTimeLine(self.TIMELINE_NAME, begin=begin, duration=timedelta(seconds=self.TIMELINE_DURATION))
        tl.save()
        logger.info(f'timeline created: {tl.name!r} begin={tl.begin.isoformat()!r} end={tl.end.isoformat()!r} duration={tl.duration.total_seconds()!r}')

    @SEtool_action('upload', 'convert-and-upload')
    def convertAndUpload(self):
        tl = ingest.IngestTimeLine.load(self.TIMELINE_NAME)
        logger.info(f'timeline before: {tl.name!r} begin={tl.begin.isoformat()!r} end={tl.end.isoformat()!r} duration={tl.duration.total_seconds()!r}')
        slices = tl.slices()
        if len(slices) == 0:
            logger.warning("currently no slices, nothing to do")
            return
        slices_duration = timedelta(seconds=0)
        for slice in slices:
            basename, wav_frames = self.makeWavFromSlice(slice)
            self.uploadWavFile(basename, wav_frames)
            slices_duration += slice.duration
        # move timeline
        logger.info(f"slices_duration={slices_duration.total_seconds():.2f}")
        begin = tl.begin + timedelta(seconds=slices_duration.total_seconds()-self.OVERLAP_DURATION)
        tl.init(tl.name, begin=begin, duration=tl.duration)
        tl.save()
        logger.info(f'timeline after: {tl.name!r} begin={tl.begin.isoformat()!r} end={tl.end.isoformat()!r} duration={tl.duration.total_seconds()!r}')

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
                        logger.bind(name='[ffmpeg]').info(ln)
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

        slice_duration = slice.duration.total_seconds()
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

    @SEtool_action('launch-transcriptions', 'launch')
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
        if len(files) == 0:
            logger.warning("no available files for transcription")
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

    @SEtool_action('fetch-results', 'fetch')
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

    @SEtool_action('list-bucket', 'lsb')
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

    @SEtool_action('cleanup-bucket', 'clb')
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

    @SEtool_action('print-namespace', 'ns')
    def printNamespace(self):
        ns = self._ns
        rich_print(ns)

    @SEtool_action('raw', 'bronze', 'silver')
    def view(self):
        console = Console(force_terminal=True)
        def create_table():
            table = Table()
            table.add_column("timestamp")
            table.add_column("speaker")
            table.add_column("word")
            return table
        ns = self._ns
        v = SpeechView(begin=ns.begin, end=ns.end)
        iterator = getattr(v, ns.action)
        for d in iterator():
            if isinstance(d,dict):
                if 'timestamp' in d:
                    d['timestamp'] = d['timestamp'].strftime(DATETIME_FORMAT)
                if 'pos' in d:
                    d['pos'] = f"{d['pos']:04d}"
            console.print(d)


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


class SpeechView:
    WINDOW_SIZE = 100
    MIN_OVERLAP_SIZE = int(WINDOW_SIZE * 0.1)

    def __init__(self, *, begin, end):
        conf = config.Config()
        self._begin = begin
        self._end = end
        all_results_filenames = glob.glob(f"{conf.SPEECH_DATADIR}/*.json")
        all_results_filenames.sort()
        results = {}
        for fn in all_results_filenames:
            res = SpeechResult.fromFileName(fn)
            results[res.begin] = res
        for res in list(results.values()):
            if (res.begin + res.duration) < begin:
                del results[res.begin]
            elif res.begin >= end:
                del results[res.begin]
        self._results = results
        self._basenames = {}

    def raw(self):
        for res in self._results.values():
            for x in res.data['results'][0]['alternatives'][0]['words']:
                yield res,x

    def bronze(self):
        previous_speaker = None
        previous_offset = None
        fileids = {}
        next_fileid = 0
        pos = 0
        self._basenames.clear()
        for res, x in self.raw():
            if ('startOffset' in x) and ('endOffset' in x):
                offset = (float(x['startOffset'][:-1]) + float(x['endOffset'][:-1])) / 2
            elif 'endOffset' in x:
                offset = float(x['endOffset'][:-1])
            elif 'startOffset' in x:
                offset = float(x['startOffset'][:-1])
            else:
                offset = previous_offset
            if offset >= res.duration.total_seconds():
                offset = previous_offset
            if 'speakerLabel' not in x:
                speaker = previous_speaker
            else:
                speaker = int(x['speakerLabel'])
            try:
                fileid = fileids[res.basename]
            except KeyError:
                fileid = next_fileid
                next_fileid += 1
                fileids[res.basename] = fileid
                self._basenames[fileid] = res.basename
                pos = 0
            d = {}
            d['fileid'] = fileid
            d['timestamp'] = res.begin + timedelta(seconds=offset)
            d['speaker'] = speaker
            d['pos'] = pos
            d['word'] = x['word']
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


class SpeechResult:
    JSON_BASENAME_PATTERN = SpeechExtractor.WAV_BASENAME_PATTERN.replace(r'\.wav',r'\.json')

    @staticmethod
    def fromFileName(filename):
        basename = os.path.basename(filename)
        m = re.match(SpeechResult.JSON_BASENAME_PATTERN, basename)
        if not m:
            raise AssertionError(f'cannot parse result filename: {basename!r}')
        begin = datetime.strptime(m.group(1), DATETIME_FORMAT)
        duration = timedelta(seconds=float(m.group(2))/1000)
        return SpeechResult(filename=filename, basename=basename, begin=begin, duration=duration)

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
