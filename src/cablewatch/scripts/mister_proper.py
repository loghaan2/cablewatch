#!/usr/bin/env python3

import subprocess
from rich import print as rich_print


def system(cmd):
    rich_print(f'[green]{cmd}[/]')
    subprocess.run(cmd, shell=True, check=True)


def main():
    system("cablewatch-stash purge")
    system("cablewatch-speech cleanup-bucket")

if __name__ == '__main__':
    main()
