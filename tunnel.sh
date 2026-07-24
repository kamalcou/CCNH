#!/bin/bash
LOGIN_NODE="mhchowdhury@pantarhei.ciroh.ua.edu"
PORT=8888
NODE=$(ssh "$LOGIN_NODE" "squeue -u mhchowdhury -h -t RUNNING -o %N" | head -1)
echo "Tunneling to compute node: $NODE"
ssh -L ${PORT}:${NODE}:${PORT} "$LOGIN_NODE"
