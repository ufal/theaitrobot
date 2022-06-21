#!/usr/bin/env python3

from hashlib import sha256

"""
API access tokens based on username
"""

def get_token(username):
    return sha256((username + "  Roboti jsou stejně dobří lidé jako my. " + username).encode('UTF-8')).hexdigest()

