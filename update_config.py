#!/usr/bin/env python

from argparse import ArgumentParser
import json
import requests


def update_config(config_file, hostname, port):
    servers = []
    data = {}
    try:
        data = json.load(open(config_file))
        servers = data["SERVER_ADDR"]
    except Exception:
        pass
    working_servers = []
    for server in servers:
        try:
            requests.post(server, json={'ping': 1}, timeout=5)
        except Exception:
            continue
        working_servers.append(server)
    # find lowest unused port & append to server list
    new_server = f'http://{hostname}:{port}'
    while new_server in working_servers:
        port += 1
        new_server = f'http://{hostname}:{port}'
    working_servers.append(new_server)
    # write back the config
    data["SERVER_ADDR"] = working_servers
    json.dump(data, open(config_file, 'w'))
    return port


if __name__ == '__main__':
    ap = ArgumentParser(description='To be called upon server startup. Will ping all pre-existing servers + remove non-responsive + add current host with a free port')
    ap.add_argument('config_file', type=str, help='Config file to be updated')
    ap.add_argument('hostname', type=str, help='Hostname to be added')
    ap.add_argument('--port', type=int, default=8654, help='Default port to be used (with numbers going up)')

    args = ap.parse_args()
    new_port = update_config(args.config_file, args.hostname, args.port)
    print(new_port)
