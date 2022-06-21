#!/usr/bin/env python3


import subprocess
import datetime


def get_git_version(path='.'):
    data = subprocess.check_output(['git', '-C', path, 'log', '--pretty=%h-%at', '-1']).strip().decode("utf-8")
    shorthash, ts = data.split('-')
    date = datetime.datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d-%H%M')
    return '%s-%s' % (shorthash, date)


def get_git_branch(path='.'):
    try:
        return subprocess.check_output(['git', '-C', path, 'symbolic-ref', '--short', 'HEAD']).strip().decode("utf-8")
    except subprocess.CalledProcessError:
        return 'DETACHED'
