#!/bin/bash


LIST_SERVERS='import json, sys; servers = json.load(sys.stdin)["SERVER_ADDR"]; print("\n".join(servers) if isinstance(servers, list) else servers)'

# kill script servers
cat config.json | python -c $LIST_SERVERS | while read SERVER; do curl -i -H "Content-Type: application/json" -X POST -d '{"killme": "now"}' $SERVER; sleep 1; done

