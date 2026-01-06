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
    return inner




class SpeechExtractor:
    LOCATION = 'eu'
    SV2_LANGUAGE = 'fr-FR'
    SV2_MODEL = 'chirp_3'
    SV2_MIN_SPEAKER = 1
    SV2_MAX_SPEAKER = 8
    TIMELINE_NAME = 'speech-extractor'
    TIMELINE_DURATION = 600
    WAV_SAMPLE_RATE = 16000
    WAV_SAMPLE_WIDTH = 2
    WAV_NUM_CHANNELS = 1 # mono
    WAV_HEADER_SIZE = 44
    WAV_CHUNK_SIZE = 256
    WAV_DATETIME_FORMAT = "%Y%m%d_%Hh%Mm%S"
    WAV_BASENAME_FORMAT = '{datetime}_{pos_ms}ms.wav'
    WAV_BASENAME_PATTERN = r'^(.+)_(.+)ms(\.wav)?$'

    class ArgumentParser(argparse.ArgumentParser):
        def __init__(self):
            actions = '|'.join(SETOOL_ACTIONS)
            super().__init__(usage=f'%(prog)s <{actions}> [timeline-names] <options>')
            self.add_argument('-l','--local', dest='local', default=False,  action='store_true',  help="keep wav files in current local directory instead of upload them to the bucket")
            self.add_argument('-k','--keep', dest='keep', default=False,  action='store_true',  help="keep blobs in buckets")
            self.add_argument('--stay',       dest='stay',  default=False,  action='store_true',  help="do not advance on timeline after audio conversion")

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

    def __init__(self, args):
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
            logger.warning("currently no slices => nothing to do")
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
        if truncate:
            pos = possible_cut_positions[-1]
            wav_frames = wav_buffer[:self.secondsToNumSamples(pos)]
        else:
            pos = self.numSamplesToSeconds(wav_buffer_size)
            wav_frames = wav_buffer
        duration = self.numSamplesToSeconds(wav_buffer_size)
        truncate = timedelta(seconds=duration-pos)
        ns = self._ns
        if not ns.stay:
            tl.advance(truncate=truncate)
        tl.save()
        logger.info(f'timeline after: {tl.name!r} begin={tl.begin.isoformat()!r} end={tl.end.isoformat()!r} duration={tl.duration.total_seconds()!r}')
        pos_ms = int(pos * 1000)
        basename = self.WAV_FILENAME_FORMAT.format(datetime=slice.begin.strftime(self.WAV_DATETIME_FORMAT), pos_ms=pos_ms)
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
        buf.seek(0)
        if ns.local:
            with open(basename, 'wb') as f:
                f.write(buf.read())
            logger.info(f"keep {basename!r} locally")
        else:
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
        breakpoint()
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
            dt = datetime.strptime(m.group(1), self.WAV_DATETIME_FORMAT)
            duration = timedelta(seconds=int(m.group(2))/1000)
            ts_bounds.append((dt, dt+duration))
            #basename = self.WAV_FILENAME_FORMAT.format(datetime=slice.begin.strftime(self.WAV_DATETIME_FORMAT), pos_ms=pos_ms)
            d = json.loads(d)
            last_speaker_label = None
            for x in d['results'][0]['alternatives'][0]['words']:
                if ('startOffset' in x) and ('endOffset' in x):
                    offset = (float(x['endOffset'][:-1]) - float(x['startOffset'][:-1])) / 2
                elif 'endOffset' in x:
                    offset = float(x['endOffset'][:-1])
                elif 'startOffset' in x:
                    offset = float(x['startOffset'][:-1])
                else:
                    raise AssertionError(str(x))
                if 'speakerLabel' not in x:
                    x['speakerLabel'] = last_speaker_label
                ts = dt + timedelta(seconds=offset)
                r = (ts, x['word'], int(x['speakerLabel']))
                rows.append(r)
                if 'speakerLabel' in x:
                    last_speaker_label = x['speakerLabel']
        for r in rows:
            print(r)
        for b in ts_bounds:
            print(b)
        with database.connect() as con:
            sql = """
                CREATE TABLE IF NOT EXISTS speech (
                    ts TIMESTAMP,
                    word TEXT,
                    speaker INTEGER,
            )
            """
            con.execute(sql)
            con.executemany("DELETE FROM speech WHERE ts >= ? AND ts <= ?", ts_bounds)
            con.executemany("INSERT INTO speech VALUES (?, ?, ?)", rows)


        #print(contents)


    #def fetchResults(self):
        #blob = bucket.blob(f"speech-extractor/incoming/{basename}")
        #blob.upload_from_file(buf, content_type="audio/wav")





# import os 
# import signal
# import asyncio
# import re
# import textwrap
# import time as time_module
# import shutil
# import tempfile
# import subprocess
# from pathlib import Path
# from datetime import datetime, time
# from typing import List, Tuple, Optional
# from loguru import logger
# from aiohttp import web, WSCloseCode
# import psutil
# from google.cloud import speech_v2
# from cablewatch import config
# from cablewatch.decorators import http_get
# import yaml
# import argparse


# class TrascribeService:
#     def __init__(self):
#         """
#         Colocar aqui todas las configuraciones necesarias para poder ejecutar el
#         proceso de transcripcion
#         """
#         # ici sont les dossier d'entree et sortie
#         self.conf = config.Config()

#         base_path = Path(__file__).parent.resolve()
#         local_config_path = base_path / "utils" / "commands.yaml"
        
#         with open(local_config_path,'r') as file:
#             config_local = yaml.safe_load(file)


# transcription_variables:
#   gcp_environment:
#     project_id: xenon-monitor-478510-d2
#     location: eu
#   s2t_model_config:
#     language: fr-FR
#     model: chirp_3
#     min_speaker: 1
#     max_speaker: 5




#         # Configuration GCP Speech-to-Text
#         self.s2t_language = config_local['transcription_variables']['s2t_model_config']['language']
#         self.s2t_model = config_local['transcription_variables']['s2t_model_config']['model']
#         self.s2t_min_spk = config_local['transcription_variables']['s2t_model_config']['min_speaker']
#         self.s2t_max_spk = config_local['transcription_variables']['s2t_model_config']['max_speaker']

#         #TODO temporel a changer avec le propre id gcp
#         self.project_id = config_local['transcription_variables']['gcp_environment']['project_id'] #"teak-instrument-480811-u5" 
#         self.location = config_local['transcription_variables']['gcp_environment']['location'] #"eu"
#         self.recognizer_id = "_"

#         self.client_options = {"api_endpoint": f"{self.location}-speech.googleapis.com"}
#         self.recognizer_path = f"projects/{self.project_id}/locations/{self.location}/recognizers/{self.recognizer_id}"
         
#         # Initialisation du client Speech-to-Text
#         try:
#             self.speech_client = speech_v2.SpeechClient(client_options=self.client_options)
#             logger.info("Client GCP Speech-to-Text initialisé avec succès")
#         except Exception as e:
#             logger.error(f"Erreur lors de l'initialisation du client GCP: {e}")
#             self.speech_client = None
    
#     def validate_datadir(self, datadir: str) -> bool:
#         """
#         Valide l'existence d'un répertoire de données
        
#         Args:
#             datadir: Chemin du répertoire à valider
            
#         Returns:
#             True si le dossier existe, False sinon
#         """
#         if os.path.exists(datadir) and os.path.isdir(datadir):
#             logger.info(f"Path trouve: {datadir}")
#             return True
#         else:
#             logger.error(f"Path introuvable: {datadir}. Execute le command cablewatch-ingest avant")
#             return False
    
#     def _parse_filename_datetime(self, filename: str) -> Optional[datetime]:
#         """
#         Extrait la date et l'heure d'un nom de fichier au format:
#         segment_2025-12-24_16h36mn20.ts
        
#         Args:
#             filename: Nom du fichier à parser
            
#         Returns:
#             datetime object ou None si le format ne correspond pas
#         """
#         pattern = r'segment_(\d{4}-\d{2}-\d{2})_(\d{2})h(\d{2})mn(\d{2})\.ts'
#         match = re.match(pattern, filename)
        
#         if match:
#             date_str = match.group(1)
#             hour = match.group(2)
#             minute = match.group(3)
#             second = match.group(4)
            
#             try:
#                 dt = datetime.strptime(f"{date_str} {hour}:{minute}:{second}", 
#                                       "%Y-%m-%d %H:%M:%S")
#                 return dt
#             except ValueError as e:
#                 logger.warning(f"Erreur de parsing de date pour {filename}: {e}")
#                 return None
#         return None
    
#     def get_files_by_datetime(
#         self, 
#         initial_date: Optional[datetime] = None,
#         initial_time: Optional[str] = None,
#         final_date: Optional[datetime] = None,
#         final_time: Optional[str] = None,
#         datadir: Optional[str] = None
#     ) -> List[str]:
#         """
#         Récupère les fichiers .ts correspondant à une date et heure spécifiques
        
#         Args:
#             target_date: Date cible (par défaut: date du jour)
#             target_time: Heure cible au format "HH:MM" (par défaut: heure actuelle)
#             datadir: Répertoire source (par défaut: config.INGEST_DATADIR)
            
#         Returns:
#             Liste des chemins complets des fichiers correspondants
#         """
#         # Si aucune variable n'est définie, le processus traitera la dernière heure d'enregistrements sauvegardés
#         now = datetime.now()
#         initial_date = initial_date or now
#         final_date = final_date or initial_date

#         initial_time = initial_time or now.strftime('%H')
#         final_time = final_time or initial_time + 1

#         if datadir is None:
#             datadir = self.conf.INGEST_DATADIR_TEST
        
#         # Validation du dossier local du videos
#         if not self.validate_datadir(datadir):
#             return []
        
#         # Parser l'heure cible
#         try:
#             target_hour_ini = int(initial_time)
#             target_hour_fin  = int(final_time)
#             target_minute = 0
#             if not(0 <= target_hour_ini <=23):
#                 raise ValueError('heure entre 0 et 23')
#             if not(0 <= target_hour_fin <=23):
#                 raise ValueError('heure entre 0 et 23')
#         except ValueError:
#             logger.error(f"Format d'heure invalide:. Utilisez HH:MM")
#             return []
        
#         matching_files = []
        
#         start_scope = datetime.combine(initial_date.date(), time(target_hour_ini, target_minute))
#         end_scope = datetime.combine(final_date.date(),time(target_hour_fin,target_minute))
#         # Parcourir tous les fichiers
#         for filename in os.listdir(datadir):
#             if not filename.endswith('.ts'):
#                 continue
            
#             file_dt = self._parse_filename_datetime(filename)
            
#             if file_dt is None:
#                 continue
            
#             if start_scope <= file_dt <= end_scope:
#                 full_path = os.path.join(datadir, filename)
#                 matching_files.append(full_path)
    
#                 logger.debug(f"Fichier correspondant trouvé: {filename}")
        
#         logger.info(f"Trouvé {len(matching_files)} fichier(s) entre {start_scope} à {end_scope}")
#         return matching_files
    
#     def _convert_ts_to_mp3(self, ts_file: str, output_dir: str) -> Optional[str]:
#         """
#         Convertit un fichier .ts en .mp3 en utilisant ffmpeg
        
#         Args:
#             ts_file: Chemin du fichier .ts source
#             output_dir: Répertoire de sortie pour le fichier .mp3
            
#         Returns:
#             Chemin du fichier .mp3 créé ou None en cas d'erreur
#         """
#         try:
#             # Générer le nom du fichier de sortie
#             base_name = os.path.splitext(os.path.basename(ts_file))[0]
#             mp3_file = os.path.join(output_dir, f"{base_name}.mp3")
            
#             # Commande ffmpeg pour la conversion
#             cmd = [
#                 'ffmpeg',
#                 '-i', ts_file,
#                 '-vn',  
#                 '-acodec', 'libmp3lame',
#                 '-q:a', '2', 
#                 '-y',  
#                 mp3_file
#             ]
                          
#             # Exécuter la conversion
#             result = subprocess.run(
#                 cmd,
#                 stdout=subprocess.PIPE,
#                 stderr=subprocess.PIPE,
#                 timeout=300  
#             )
            
#             if result.returncode == 0 and os.path.exists(mp3_file):
#                 logger.info(f"Conversion réussie: {ts_file} -> {mp3_file}")
#                 return mp3_file
#             else:
#                 logger.error(f"Échec de conversion pour {ts_file}: {result.stderr.decode()}")
#                 return None
                
#         except subprocess.TimeoutExpired:
#             logger.error(f"Timeout lors de la conversion de {ts_file}")
#             return None
#         except Exception as e:
#             logger.error(f"Erreur lors de la conversion de {ts_file}: {e}")
#             return None
    
#     def _transcribe_audio_file(self, audio_file: str) -> Tuple[List[str], int]:
#         """
#         Transcrit un fichier audio en utilisant GCP Speech-to-Text
        
#         Args:
#             audio_file: Chemin du fichier audio à transcrire
            
#         Returns:
#             Tuple (script_final, billed_duration)
#         """
#         if self.speech_client is None:
#             logger.error("Client Speech-to-Text non initialisé")
#             return [], 0
        
#         config_speech = speech_v2.types.RecognitionConfig(
#             auto_decoding_config={},
#             language_codes=[self.s2t_language],
#             model=self.s2t_model,
#             features=speech_v2.types.RecognitionFeatures(
#                 diarization_config=speech_v2.types.SpeakerDiarizationConfig(
#                     min_speaker_count=self.s2t_min_spk,
#                     max_speaker_count=self.s2t_max_spk,
#                 )
#             )
#         )

#         inicio = time_module.time()
        
#         try:
#             with open(audio_file, 'rb') as f:
#                 content = f.read()
            
#             request = speech_v2.types.RecognizeRequest(
#                 recognizer=self.recognizer_path,
#                 config=config_speech,
#                 content=content,
#             )
            
#             response = self.speech_client.recognize(request=request)
#             logger.debug(f"Réponse de transcription reçue pour {audio_file}")

#             billed_duration = response.metadata.total_billed_duration.seconds

#             script_final = []
#             current_speaker = None
#             current_sentence = ""

#             for result in response.results:
#                 for word_info in result.alternatives[0].words:
#                     speaker = word_info.speaker_label or "Unknown"
#                     word = word_info.word

#                     if speaker != current_speaker:
#                         if current_speaker is not None:
#                             script_final.append(f"Locuteur {current_speaker}: {current_sentence.strip()}")
#                         current_speaker = speaker
#                         current_sentence = word + " "
#                     else:
#                         current_sentence += word + " "

#             if current_sentence:
#                 script_final.append(f"Locuteur {current_speaker}: {current_sentence.strip()}")
            
#             fin = time_module.time()
#             logger.info(f"Transcription terminée en {fin - inicio:.2f} secondes (durée facturée: {billed_duration}s)")
#             return script_final, billed_duration
            
#         except Exception as e:
#             logger.error(f"Erreur lors de la transcription de {audio_file}: {e}")
#             return [], 0
    
#     async def process_and_transcribe(
#         self,
#         initial_date: Optional[datetime] = None,
#         initial_time: Optional[str] = None,
#         final_date: Optional[datetime] = None,
#         final_time: Optional[str] = None,
#         datadir: Optional[str] = None
#     ) -> List[str]:
#         """
#         Fonction asynchrone principale qui:
#         1. Récupère les fichiers .ts correspondant à la date/heure
#         2. Convertit les fichiers .ts en .mp3 dans un dossier temporaire
#         3. Transcrit les fichiers audio
#         4. Sauvegarde les transcriptions dans TRANSCRIPT_DATADIR
#         5. Nettoie le dossier temporaire
        
#         Args:
#             target_date: Date cible (par défaut: date du jour)
#             target_time: Heure cible au format "HH:MM" (par défaut: heure actuelle)
#             datadir: Répertoire source (par défaut: config.INGEST_DATADIR)
            
#         Returns:
#             Liste des chemins des fichiers de transcription créés
#         """
#         # Étape 1: Récupérer les fichiers correspondants
#         ts_files = self.get_files_by_datetime(initial_date, initial_time,final_date,final_time, datadir)
        
#         if not ts_files:
#             logger.warning("Aucun fichier trouvé pour les critères spécifiés")
#             return []
        
#         # Créer le répertoire de transcription s'il n'existe pas
#         transcript_dir = self.conf.TRANSCRIPT_DATADIR
#         os.makedirs(transcript_dir, exist_ok=True)
        
#         # Créer un dossier temporaire
#         temp_dir = tempfile.mkdtemp(prefix="transcribe_")
#         logger.info(f"Dossier temporaire créé: {temp_dir}")
        
#         transcript_files = []
        
#         try:
#             # Étape 2: Convertir les fichiers .ts en .mp3
#             mp3_files = []
#             for ts_file in ts_files:
#                 logger.info(f"Conversion de {os.path.basename(ts_file)}...")
#                 mp3_file = self._convert_ts_to_mp3(ts_file, temp_dir)
#                 if mp3_file:
#                     mp3_files.append(mp3_file)
            
#             if not mp3_files:
#                 logger.error("Aucune conversion réussie")
#                 return []
            
#             # Étape 3 & 4: Transcrire et sauvegarder
#             for mp3_file in mp3_files:
#                 logger.info(f"Transcription de {os.path.basename(mp3_file)}...")
                
#                 # Transcription (exécuté de manière asynchrone via run_in_executor)
#                 loop = asyncio.get_event_loop()
#                 script_final, billed_duration = await loop.run_in_executor(
#                     None, 
#                     self._transcribe_audio_file, 
#                     mp3_file
#                 )
                
#                 if script_final:
#                     # Créer le fichier de transcription
#                     base_name = os.path.splitext(os.path.basename(mp3_file))[0]
#                     transcript_file = os.path.join(transcript_dir, f"{base_name}.txt")
                    
#                     with open(transcript_file, 'w', encoding='utf-8') as f:
#                         f.write(f"# Transcription de {base_name}\n")
#                         f.write(f"# Durée facturée: {billed_duration}s\n")
#                         f.write(f"# Date de transcription: {datetime.now().isoformat()}\n\n")
#                         f.write('\n'.join(script_final))
                    
#                     transcript_files.append(transcript_file)
#                     logger.info(f"Transcription sauvegardée: {transcript_file}")
#                 else:
#                     logger.warning(f"Aucune transcription générée pour {mp3_file}")
            
#         finally:
#             # Étape 5: Nettoyer le dossier temporaire
#             try:
#                 shutil.rmtree(temp_dir)
#                 logger.info(f"Dossier temporaire supprimé: {temp_dir}")
#             except Exception as e:
#                 logger.error(f"Erreur lors de la suppression du dossier temporaire: {e}")
        
#         logger.info(f"Traitement terminé: {len(transcript_files)} transcription(s) créée(s)")
#         return transcript_files
    

# async def main():
#     parser = argparse.ArgumentParser(description="video transcriptor")
#     parser.add_argument('-a', '--initial_date', type=str)
#     parser.add_argument('-b', '--initial_time', type=str)
#     parser.add_argument('-c', '--final_date', type=str)
#     parser.add_argument('-d', '--final_time', type=str)

#     args = parser.parse_args()

#     service = TrascribeService()
#     def to_dt(date_str):
#         return datetime.strptime(date_str, '%Y-%m-%d') if date_str else None

#     try:
#         # Check if any arguments were provided
#         if any([args.initial_date, args.initial_time, args.final_date, args.final_time]):
#             logger.info('Execution transcribe avec parser')
            
#             # Convert strings to datetime objects for the method
#             result = await service.process_and_transcribe(
#                 initial_date=to_dt(args.initial_date),
#                 initial_time=args.initial_time,
#                 final_date=to_dt(args.final_date),
#                 final_time=args.final_time
#             )
#         else:
#             logger.info('Execution transcribe without arguments')
#             result = await service.process_and_transcribe()
            
#         logger.info('Execution complete')

#     except Exception as e:
#         logger.error(f"Main execution failed: {e}")

# if __name__ == "__main__":
#     asyncio.run(main())(cablewatch) loghaan@arkaan:$ 

