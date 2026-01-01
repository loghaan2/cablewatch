import glob
import functools
import pytest
import subprocess
from cablewatch import config


@pytest.fixture(scope="session")
def conf():
    yield config.Config()


def collect_files(*, accept_patterns, reject_patterns=[]):
    paths = set()
    glob_ = functools.partial(glob.glob, recursive=True)
    conf = config.Config()
    for pattern in accept_patterns:
        paths.update(glob_(f"{conf.PROJECT_DIR}/{pattern}"))
    for pattern in reject_patterns:
        paths -= set(glob_(f"{conf.PROJECT_DIR}/{pattern}"))
    n = len(conf.PROJECT_DIR)
    files = set()
    for pth in paths:
        files.add(pth[n + 1 :])
    return files


PYTHON_ACCEPT_PATTERNS = [
    "src/cablewatch/*.py",
    "tests/*.py",
]

PYTHON_REJECT_PATTERNS = []

PYTHON_FILES = collect_files(
    accept_patterns=PYTHON_ACCEPT_PATTERNS, reject_patterns=PYTHON_REJECT_PATTERNS
)


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_ruff(conf, path):
    cmd = f"ruff check {conf.PROJECT_DIR}/{path}"
    print(cmd)
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout.decode())
    assert proc.returncode == 0
