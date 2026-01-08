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
from cablewatch import config, ingest, loghlp, database


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


class FloatRange:
    def __init__(self, min, max):
        self.min = min
        self.max = max

    def __contains__(self, x):
        return self.min <= x <= self.max

    def __repr__(self):
        return repr([self.min,self.max])


SETOOL_ACTIONS = {}


def SEtool_action(*names):
    def inner(obj):
        for n in names:
            SETOOL_ACTIONS[n]=obj
        return obj
    return inner


class SpeechExtractor:
    LOCATION = 'eu'
    SV2_LANGUAGE = 'fr-FR'
    SV2_MODEL = 'chirp_3'
    SV2_MIN_SPEAKER = 1
    SV2_MAX_SPEAKER = 8
    TIMELINE_NAME = 'speech-extractor'
    TIMELINE_DURATION = 120 #600
    WAV_SAMPLE_RATE = 16000
    WAV_SAMPLE_WIDTH = 2
    WAV_NUM_CHANNELS = 1 # mono
    WAV_HEADER_SIZE = 44
    WAV_CHUNK_SIZE = 256
    WAV_BASENAME_FORMAT = '{datetime}_{pos_ms}ms.wav'
    WAV_BASENAME_PATTERN = r'^(.+)_(.+)ms(\.wav)?$'
    DATETIME_FORMAT = "%Y%m%d_%Hh%Mm%S"

    class ArgumentParser(argparse.ArgumentParser):
        def __init__(self):
            actions = '|'.join(SETOOL_ACTIONS)
            super().__init__(usage=f'%(prog)s <{actions}> [timeline-names] <options>')
            self.add_argument('-k','--keep', dest='keep', default=False,  action='store_true',  help="keep wav files locally and keep blobs in buckets")

        def parse_args(self, args):
            prog = args[0]
            ns,args = super().parse_known_args(args[1:])
            ns.prog = prog
            ns.action = None
            ns.largs = []
            ns.rargs = []
            xargs = ns.largs
            for a in args:
                if ns.action is None:
                    if a not in SETOOL_ACTIONS:
                        self.error(f'invalid action {a!r}')
                    else:
                        ns.action = a
                elif a == '--':
                    xargs = ns.rargs
                else:
                    xargs.append(a)
            if ns.action is None:
                self.error('no action secified')
            return ns

    def __init__(self, args=None, action=None, keep=False):
        if args is None:
            self._ns = argparse.Namespace(action=action, keep=keep)
            self._argparser = None
        else:
            p = self.ArgumentParser()
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
        tl = ingest.IngestTimeLine(name=self.TIMELINE_NAME, duration=timedelta(seconds=self.TIMELINE_DURATION))
        logger.info(f'timeline before: {tl.name!r} begin={tl.begin.isoformat()!r} end={tl.end.isoformat()!r} duration={tl.duration.total_seconds()!r}')
        self._timeline = tl

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

    @SEtool_action('upload')
    def upload(self):
        slices = self._timeline.slices()
        if len(slices) == 0:
            logger.warning("currently no slices ==> nothing to do")
            return
        for slice in slices:
            basename, wav_frames = self.makeWavFromSlice(slice)
            self.uploadWavFile(basename, wav_frames)

    def makeWavFromSlice(self, slice):
        with slice.concatFile() as concat:
            cmd = f'ffmpeg -f concat -safe 0 -i {concat.name}'
            cmd += ' -af silencedetect=noise=-30dB:d=0.5'
            cmd += f' -vn -ac {self.WAV_NUM_CHANNELS} -ar {self.WAV_SAMPLE_RATE} -f wav '
            cmd += ' pipe:1 '
            logger.info(f'run {cmd!r}')
            proc = subprocess.Popen(
                cmd,
                shell = True,
                stdin = subprocess.DEVNULL,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
            )
            poller = select.poll()
            active_fds = {proc.stdout.fileno(), proc.stderr.fileno()}
            for fd in active_fds:
                poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
            wav_buffer =b''
            wav_header = None
            start = None
            end = None
            duration = 0
            possible_cut_positions = []
            count = 0
            wav_buffer_size = 0
            relevant_bounds = [0, math.inf]
            if slice.first_inpoint is not None:
                relevant_bounds[0] = slice.first_inpoint.total_seconds()
            if slice.last_outpoint is not None:
                relevant_bounds[1] = (slice.duration - slice.last_outpoint).total_seconds()
            relevant_bounds_nsamples = [self.secondsToNumSamples(relevant_bounds[0]), self.secondsToNumSamples(relevant_bounds[1])]
            relevant_bounds = FloatRange(*relevant_bounds)
            relevant_bounds_nsamples = FloatRange(*relevant_bounds_nsamples)
            logger.info(f"relevant bounds for processing is {relevant_bounds}")
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
                            logger.info(ln)
                            if ln.endswith('\n'):
                                ln = ln[:-1]
                            m = re.search(r'silence_start: (.+)$', ln)
                            if m:
                                start = float(m.group(1))
                            m = re.search(r'silence_end: (.+) \| silence_duration: (.+)$', ln)
                            if m:
                                end = float(m.group(1))
                                duration = float(m.group(2))
                            if start and duration and end:
                                pos = start+duration/2
                                if pos in relevant_bounds:
                                    logger.info(f'possible cut position #{count} at {pos:.2f}s')
                                    possible_cut_positions.append(pos)
                                else:
                                    logger.info(f'cut position #{count} at {pos:.2f}s is not relevant')
                                duration = 0
                                start = None
                                end = None
                                count += 1
                        else: # ffmpeg wav output
                            if wav_header is None:
                                wav_header = os.read(fd,self.WAV_HEADER_SIZE)
                            else:
                                wav_chunk = os.read(fd, self.WAV_CHUNK_SIZE)
                                wav_buffer_size += len(wav_chunk)
                                if wav_buffer_size not in relevant_bounds_nsamples:
                                    wav_chunk = bytes(len(wav_chunk))
                                if len(wav_chunk) == 0:
                                    logger.info("ffmpeg wav output EOF")
                                    poller.unregister(fd)
                                    active_fds.remove(fd)
                                    break
                                wav_buffer += wav_chunk
        tl = self._timeline
        if len(possible_cut_positions) == 0:
            truncate = False
        elif not slice.last:
            truncate = False
        else:
            truncate = True
        truncate = False
        if truncate:
            pos = possible_cut_positions[-1]
            wav_frames = wav_buffer[:self.secondsToNumSamples(pos)]
        else:
            pos = self.numSamplesToSeconds(wav_buffer_size)
            wav_frames = wav_buffer
        duration = self.numSamplesToSeconds(wav_buffer_size)
        truncate = timedelta(seconds=duration-pos)
        ns = self._ns
        tl.advance(truncate=truncate)
        tl.save()
        logger.info(f'timeline after: {tl.name!r} begin={tl.begin.isoformat()!r} end={tl.end.isoformat()!r} duration={tl.duration.total_seconds()!r}')
        pos_ms = int(pos * 1000)
        basename = self.WAV_BASENAME_FORMAT.format(datetime=slice.begin.strftime(self.DATETIME_FORMAT), pos_ms=pos_ms)
        size_m = (len(wav_frames) + self.WAV_HEADER_SIZE) / (1024*1024)
        logger.info(f'wav file made: basename={basename!r} pos={pos:.2f}s duration={duration:.2f}s truncate={truncate.total_seconds():.2f}s size={size_m:.2f}M')
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
        if ns.keep:
            buf.seek(0)
            with open(basename, 'wb') as f:
                f.write(buf.read())
            logger.info(f"keep {basename!r} locally")
        buf.seek(0)
        client = self._storage_client
        bucket = client.bucket(conf.GCP_BUCKET_NAME)
        blob = bucket.blob(f"speech-extractor/uploaded/{basename}")
        blob.upload_from_file(buf, content_type="audio/wav")
        logger.info(f"{basename!r} uploaded")

    @SEtool_action('launch')
    def launch(self):
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
            logger.warning("all uploaded files are already launched")
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

    @SEtool_action('fetch')
    def fetch(self):
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
            results[m.group(1)] = blob.download_as_text()
            if not ns.keep:
                logger.info(f"delete blob {blob.name!r}")
                blob.delete()
        for folder in 'uploaded', 'processing':
            for blob in bucket.list_blobs(prefix=f"speech-extractor/{folder}/"):
                if blob.name.endswith('/'):
                    continue
                pth = pathlib.Path(blob.name)
                if pth.stem not in results:
                    continue
                if not ns.keep:
                    logger.info(f"delete blob {blob.name!r}")
                    blob.delete()
        rows = []
        ts_bounds = []
        for basename,d in results.items():
            m = re.match(self.WAV_BASENAME_PATTERN, basename)
            if not m:
                raise AssertionError
            dt = datetime.strptime(m.group(1), self.DATETIME_FORMAT)
            duration = timedelta(seconds=int(m.group(2))/1000)
            ts_bounds.append((dt, dt+duration))
            d = json.loads(d)
            last_speaker_label = None
            for x in d['results'][0]['alternatives'][0]['words']:
                if ('startOffset' in x) and ('endOffset' in x):
                    offset = (float(x['startOffset'][:-1]) + float(x['endOffset'][:-1])) / 2
                elif 'endOffset' in x:
                    offset = float(x['endOffset'][:-1])
                elif 'startOffset' in x:
                    offset = float(x['startOffset'][:-1])
                else:
                    raise AssertionError(str(x))
                if 'speakerLabel' not in x:
                    x['speakerLabel'] = last_speaker_label
                ts = dt + timedelta(seconds=offset)
                r = (ts, int(x['speakerLabel']), x['word'])
                rows.append(r)
                if 'speakerLabel' in x:
                    last_speaker_label = x['speakerLabel']
        with database.connect() as con:
            sql = """
                CREATE TABLE IF NOT EXISTS speech (
                    ts TIMESTAMP,
                    speaker INTEGER,
                    word TEXT,
            )
            """
            con.execute(sql)
            nrows0 = con.execute("SELECT count(*) FROM speech").fetchone()[0]
            for b in ts_bounds:
                 con.execute("DELETE FROM speech WHERE ts >= ? AND ts <= ?", b)
            nrows1 = con.execute("SELECT count(*) FROM speech").fetchone()[0]
            logger.info(f"{nrows0 - nrows1} row(s) deleted in speech table")
            res = con.executemany("INSERT INTO speech VALUES (?, ?, ?)", rows)
            nrows2 = con.execute("SELECT count(*) FROM speech").fetchone()[0]
            logger.info(f"{nrows2 - nrows1} row(s) inserted in speech table")

    @SEtool_action('view')
    def view(self):
        table = Table()
        table.add_column("ts")
        table.add_column("speaker")
        table.add_column("word")
        nrows = 0
        with database.connect() as con:
            for row in con.execute("SELECT * FROM speech").fetchall():
                ts,speaker,word = row
                ts = ts.strftime(self.DATETIME_FORMAT)
                table.add_row(ts, str(speaker), word)
                nrows += 1
        rich_print(table)
        print()
        rich_print(f'{nrows} row(s)')

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
