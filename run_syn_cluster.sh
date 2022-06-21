#!/bin/bash

#$ -q gpu-'*'.q
#$ -l gpu=1,gpu_ram=16G,hostname='tdll*|dll1|dll8'
#$ -V 
#$ -cwd
#$ -b y
#$ -j y
#$ -N "URUsynserver"

while true;do
    ./start_syn_server.sh
    sleep 1
done
