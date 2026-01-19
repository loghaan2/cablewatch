#!/usr/bin/env python3

import os
import sys
import getpass
import base64


def main():
    cmd = []
    for i,a in enumerate(sys.argv):
        if i==0:
            cmd.append('wscat')
        elif a=='--basic-auth':
            username = input("Username: ")
            password = getpass.getpass("Password: ")
            credential = base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('utf-8')
            cmd += ['-H', f'Authorization: Basic {credential}']
        else:
            cmd.append(a)
    print(cmd)
    os.execvp(cmd[0], cmd)
    raise AssertionError('execvp() failed')


if __name__ == '__main__':
    main()
