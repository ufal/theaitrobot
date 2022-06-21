# Interactive story generation

### Installation:

* [install.sh](./install.sh) should be run to install all dependencies (mostly
  specified in [requirements.txt](requirements.txt)).

### Frontends (CGI):

There are multiple web fronteds.
The demo is the more user-friendly one.
The others are less user friendly but are more powerfull (have more controls).
They should be run under Apache as a CGI module.

* [demo.py](./demo.py) -- a simplified user-friendly demo frontend, providing
  access to both flat and hierarchical generation
* [story_batch.py](./story_batch.py) -- basic flat 
* [synopse.py](./synopse.py) -- 1st step hierarchical: synopsis generation
* [synopsis2script.py](./synopsis2script.py) -- 2nd step hierarchical: synopsis-to-script

### Backend (running as a server on a GPU):

* [story_server.py](./story_server.py) is the backend, this needs to run on the same machine as Apache, or on an exposed port. It assumes having 1 GPU, where the models are loaded at all times.

### Running the servers:

The basic server is a "script" server, generating flat scripts (also used as
2nd step in hierarchical generation).

There is also a "syn" server, which is used to generate synopses as 1st step
in hierarchical generation. It is operated by similar scripts but having "syn"
in their names,

* [config.json](config.json) is a configuration script, specifying the
  hostname and port on which the server is running; the default is
  `localhost:8456`.
* [start_server.sh](./start_server.sh) starts the server. Parameters such as
  hostanme and port number are specified in this file.
* [run_on_cluster.sh](./run_on_cluster.sh) starts the server and keeps
  restarting it when it dies. The script is also useful if you run the server
  on an SGE cluster.
* [kill.sh](./kill.sh) kills the servers. If run through
  [run_on_cluster.sh](./run_on_cluster.sh), it is restarted, otherwise it is only killed.
* The other Python files provide various functionality for the server and are
  imported into [story_server.py](./story_server.py).

### Other files:

* [LICENCE](LICENCE) is the licence for this code, namely the MIT licence.

### Deploying & Running using the Makefile

* Deploy new versions (both frontend & backend) from your checkout by `make deploy`

* Restart the server (loads new code w/o new cluster job) by `make restart`

* Start new backend instances by running `qsub ./run_on_cluster.py`
    * Config file is `config.json` for flat & synopsis-to-script, `syn_config.json` for synopsis generation 
    * Multiple backends work as "random" load balancing (frontend will select a random backend from the config file at each time)
    * New instances update themselves automatically in the config file (via `update_config.py`). 
        They wait for each other if you start more within 2 minutes (this is checked by date of `server.started`).

* If you kill any backend instance, run `make restart` (i.e. restart the remaining instances) so that
    the config file is updated and does not contain dead instances. Alternatively update the config file by hand, if you don't want to restart.

