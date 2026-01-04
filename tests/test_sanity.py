import subprocess
import re


VALID_FFMPEG_VERSIONS = set([
    '7.1.2-1+b1',
    '7.1.3-0+deb13u1',
])


def test_checkFFMEGVersion():
    p = subprocess.run("ffmpeg -version", shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = p.stdout.decode()
    print(output)
    m = re.search(r'^ffmpeg version (\S+) Copyright', output, re.MULTILINE)
    if not m:
        raise AssertionError('cannot find ffmpeg version')
    version = m.group(1)
    if version not in VALID_FFMPEG_VERSIONS:
        raise AssertionError(f'invalid ffmpeg version: {version!r}')
