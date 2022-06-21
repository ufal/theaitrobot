#!/bin/bash

rm -f syn_server.started
echo Server started at $(date) | tee syn_server.started

export TRANSFORMERS_CACHE=/lnet/ms/data/ELITR/gpt/gpt-2/transformers

. ./set_cuda10_1

. ./venv-gpt-2/bin/activate

echo '{"SERVER_ADDR": "http://'`hostname`':8687"}' > syn_config.json

#MODEL=/lnet/work/projects/URUwork/synopsove_modely/model_saveall_hack_long
MODEL=distilgpt2

python story_server.py --model $MODEL -P --host 0.0.0.0 --database syn.db --translate --port 8687 --log-level debug --no-ban-remarks

