#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re


def _normalize_key(key):
    """Returns the key as a 2-member list: ['scene_id-'/'', 'line_id'],
    regardless whether the scene ID was supplied or not. This makes
    manipulation with the line ID easier."""
    key = key.split('-', 1)
    if len(key) < 2:
        key = ['', key[0]]
    else:
        key[0] += '-'
    return key

def validate_key(key):
    """Check if the given key is valid (either compressed or full)."""
    key = _normalize_key(key)
    is_valid = bool(re.match(r'^[A-Za-z0-9_.~-]*[A-Za-z_.~]$', key[1]))
    return key[1] == '' or (key[1].isascii() and is_valid)

def compress_key(key, trunc=False):
    """Produce a short version of a key (aaa -> 3a etc.)."""
    scene_id, line_id = _normalize_key(key)
    if trunc and len(scene_id) > 70:
        scene_id = scene_id[:70] + '(...)-'
    line_id = re.sub(r'([a-zA-Z])\1+', lambda m: str(len(m.group(0))) + m.group(1), line_id)
    if trunc and len(line_id) > 50:
        line_id = '(...)' + line_id[len(line_id) - 50:]
    return scene_id + line_id


def expand_key(key):
    """Produce full version of a key (with all letters typed out)."""
    key = _normalize_key(key)
    return key[0] + re.sub(r'([0-9]+)([a-zA-Z])', lambda m: int(m.group(1)) * m.group(2), key[1])

def split_into_parts(key):
    """Split into parts corresponding to individual commands.

    scena-abc2_a -> [scena, a, b, c, 2_, a]"""
    key = _normalize_key(expand_key(key))

    parts = []

    if key[0]:
        parts.append(key[0].rstrip('-'))

    buf = ''
    for char in key[1]:
        if re.match(r'^[0-9]$', char):
            # number command for skipping
            buf += char
        elif char in {'_', '.', '~'}:
            # skip line mark or other cmmand
            parts.append(buf + char)
            buf = ''
        else:
            # normal line
            parts.append(char)
    assert buf == '', key

    return parts


if __name__=="__main__":
    from argparse import ArgumentParser

    ap = ArgumentParser()
    ap.add_argument('key', type=str, help="Key to test")
    args = ap.parse_args()
    key = args.key

    print('INPUT:', key,
        'VALID:', validate_key(key),
        'EXPAND:', expand_key(key),
        'COMPRESS:', compress_key(key),
        'COMPRESS + TRUNC:', compress_key(key, trunc=True),
        'SPLIT:', split_into_parts(key),
        sep='\n')


