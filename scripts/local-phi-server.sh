#!/bin/bash


set -euxo pipefail

echo "Running Llama.cpp server from ${LLAMA_CPP_BUILD}"
$LLAMA_CPP_BUILD/bin/llama-server -m $LLAMA_CPP_MODEL \
    --host 127.0.0.1 \
    --port 8080 \
    -ngl 256