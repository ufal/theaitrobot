#!/usr/bin/env python3
# coding: utf-8

"""
API to forward requests from outside to internal server
"""

import random
from argparse import ArgumentParser
import json
import flask
from flask_cors import CORS
import requests
import logging
from api_token import get_token


logging.basicConfig(
    format='%(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO)

ALLOWED_USERS = {'aignos'}


def valid_request(request):
    result = False
    for field in ('username', 'username_limit'):
        if field in request and (request[field] in ALLOWED_USERS or request.get('token') == get_token(request[field])):
            result = True
    return result


def handle_server_request():
    """Main method to use for Flask requests."""
    logging.info('Got request {}'.format(flask.request.json))

    try:
        req = None
        if valid_request(flask.request.json):
            req = requests.post(random.choice(SERVER_ADDR), json=flask.request.json)
            if req.status_code == requests.codes.ok:
                logging.info('Got answer {}'.format(req))
                return req.text
        # else else:
        logging.warning('Got error {}'.format(req or 'invalid request'))
        flask.abort(500)
    except Exception as e:
        logging.warning(f'Got exception: {e}\n')
        flask.abort(500)


def handle_bad_request(e):
    return 'ERROR', 500


if __name__ == '__main__':
    ap = ArgumentParser(description='Story generation API')
    ap.add_argument('-p', '--port', default=8457,
                    help='Port on which this API runs')
    ap.add_argument('-H', '--host', default='0.0.0.0',
                    help='Host/interface on which this API runs (defaults to 0.0.0.0 which serves all IPs)')
    args = ap.parse_args()

    try:
        with open('config.json') as configfile:
            config = json.load(configfile)
            SERVER_ADDR = config['SERVER_ADDR']
    except Exception:
        SERVER_ADDR = 'http://localhost:8456'
    if not isinstance(SERVER_ADDR, list):
        SERVER_ADDR = [SERVER_ADDR]

    app = flask.Flask(__name__)
    CORS(app)
    app.add_url_rule('/', 'handle_server_request', handle_server_request, methods=['POST'])
    app.register_error_handler(500, handle_bad_request)
    logging.info('Starting server')
    app.run(host=args.host, port=args.port, threaded=True)
