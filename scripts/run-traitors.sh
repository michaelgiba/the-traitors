#!/bin/bash

RANDOM_HASH="$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c 8)"


set -euo pipefail

PARENT_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"


source ${PARENT_DIR}/.venv/bin/activate

set -x

RANDOM_DIRNAME="${PARENT_DIR}/results/traitors/${RANDOM_HASH}"

mkdir -p ${RANDOM_DIRNAME}

python -m reality_show_bench.main \
    --config ${PARENT_DIR}/game_configs/the_traitors/default.json \
    --output-html $RANDOM_DIRNAME/plomp.html > $RANDOM_DIRNAME/result.json
