SHELL:=/bin/bash

deploy: deployclient deployserver

# deployment directory
D:=./deploy/

# backup directory
Z:=./backup/

G:=$$(echo $$USER; echo $$PWD; git rev-parse HEAD; git rev-parse --abbrev-ref HEAD; git status -uno -s)

CLIENT:=story.py story_batch.py keyops.py synopse.py synopsis2script.py cgi_common.py api_token.py
SERVER:=story_server.py summarize.py char_support.py keyops.py urutranslate.py nli.py api.py update_config.py
MAINSERVER:=run_on_cluster.sh start_server.sh run_syn_cluster.sh start_syn_server.sh

LIST_SERVERS='import json, sys; servers = json.load(sys.stdin)["SERVER_ADDR"]; print("\n".join(servers) if isinstance(servers, list) else servers)'

deploydemo:
	-mkdir -p $D
	cp -r demo.py i18 $D
	-rm -r $D/static
	-rm -r $D/staticsource
	mkdir -p $D/static
	mkdir -p $D/staticsource
	cd static; for t in png css js; do for f in *$$t; do cp $$f $D/staticsource; sed s/FILE/$$f/ serve-$$t.sh > $D/static/$$f; done; done
	chmod a+x $D/static/*

deployclient:
	-mkdir -p $D
	for f in $(CLIENT); do rm -f $D/$$f; cp $$f $D; done
	rm -f $D/client.deployed
	echo $G > $D/client.deployed

deployserver:
	-mkdir -p $D
	for f in $(SERVER) $(MAINSERVER); do rm -f $D/$$f; cp $$f $D; done
	rm -f $D/server.deployed
	echo $G > $D/server.deployed

restart:
	cat $D/config.json | python -c $(LIST_SERVERS) | while read SERVER; do curl -i -H "Content-Type: application/json" -X POST -d '{"killme": "now"}' $$SERVER; sleep 1; done

synrestart:
	a=`grep -o '"http.*"' $D/syn_config.json | sed s/'"'//g`; curl -i -H "Content-Type: application/json" -X POST -d '{"killme": "now"}' $$a

backup:
	-mkdir -p $Z
	cp $D/database.db $Z/database_`date '+%F_%H-%M-%S'`.db
	cp $D/syn.db $Z/syn_`date '+%F_%H-%M-%S'`.db
