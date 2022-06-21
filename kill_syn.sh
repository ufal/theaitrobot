#!/bin/bash

# kill syn server
a=`grep -o '"http.*"' syn_config.json | sed s/'"'//g`
curl -i -H "Content-Type: application/json" -X POST -d '{"killme": "now"}' $a

