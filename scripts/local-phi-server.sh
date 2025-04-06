#!/bin/bash
#
set -euxo pipefail

/home/michaelgiba/code/github/survivor/ext/llama.cpp/build/bin/llama-server -m /home/michaelgiba/code/github/survivor/models/microsoft_Phi-4-mini-instruct-IQ4_XS.gguf --host 127.0.0.1 --port 8080 -ngl 256
