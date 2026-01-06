import pytest
import io
import pathlib
import secrets
from google.cloud import storage
from cablewatch import config


SPEECH_EXTRACTOR_FOLDERS = ['launched', 'results', 'uploaded']


@pytest.fixture(scope="session")
def conf():
    yield config.Config()


@pytest.fixture(scope="session")
def storage_client(conf):
    yield storage.Client.from_service_account_json(conf.GCP_SERVICE_ACCOUNT)


def test_bucketSpeechExtractorFolders(conf,storage_client):
    bucket = storage_client.bucket(conf.GCP_BUCKET_NAME)
    folders = []
    prefix = 'speech-extractor/'
    for blob in bucket.list_blobs(prefix=prefix):
        if blob.name == prefix:
            continue
        elif not blob.name.endswith('/'):
            continue
        folders.append(pathlib.Path(blob.name).name)
    folders.sort()
    print(folders)
    assert folders == SPEECH_EXTRACTOR_FOLDERS


@pytest.mark.parametrize("folder", SPEECH_EXTRACTOR_FOLDERS)
def test_bucketSpeechExtractorFolderAccess(conf,storage_client,folder):
    content = secrets.token_hex(16)
    buf = io.BytesIO(content.encode())
    bucket = storage_client.bucket(conf.GCP_BUCKET_NAME)
    blob = bucket.blob(f'speech-extractor/{folder}/test.txt')
    blob.upload_from_file(buf, content_type="text/plain")
    downloaded_content = blob.download_as_text()
    assert downloaded_content==content
    blob.delete()
