#!/bin/bash

# make sure we're starting servers at least 120 secs apart so they respond to ping
if [[ -f server.started ]]; then
    LAST_STARTED_AGE=$(( `date +%s` - `stat -L --format %Y server.started` ))
    while (( LAST_STARTED_AGE < 120 )); do
        echo "Waiting at $(date) -- server.started is $LAST_STARTED_AGE secs old."
        sleep $(( RANDOM % 20 + 120 - LAST_STARTED_AGE ))
        LAST_STARTED_AGE=$(( `date +%s` - `stat -L --format %Y server.started` ))
    done
fi
rm -f server.started
echo Server started at $(date) | tee server.started

export TRANSFORMERS_CACHE=/lnet/ms/data/ELITR/gpt/gpt-2/transformers

. ./set_cuda10_1

. ./venv-gpt-2/bin/activate

HOSTNAME=`hostname`
PORT=`python update_config.py --port 8456 config.json $HOSTNAME`

#MODEL=/lnet/work/projects/URUwork/patricia_models/model_save_summ2script_medium_768_from_pretrained_final/
#MODEL=/lnet/work/projects/URUwork/patricia_models/model_save_summ2script_medium_768_proquest_nrno_10_epochs
#MODEL=/lnet/work/projects/URUwork/patricia_models/model_save_summ2script_medium_768_proquest_nrno_2nd_after_epoch_6
MODEL=distilgpt2

# add -N to switch on NLI
python story_server.py --model $MODEL --host 0.0.0.0 --translate --port $PORT --log-level debug

