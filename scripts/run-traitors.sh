#!/bin/bash

GAME_CONFIG=${1:-default}
RANDOM_HASH="$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c 8)"

set -euo pipefail

PARENT_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"

source ${PARENT_DIR}/.venv/bin/activate

echo "Running traitors game with config: ${GAME_CONFIG}"

set -x

RANDOM_DIRNAME="${PARENT_DIR}/results/traitors/${RANDOM_HASH}"

mkdir -p ${RANDOM_DIRNAME}

python -m reality_show_bench.main \
    --config ${PARENT_DIR}/game_configs/the_traitors/${GAME_CONFIG}.json \
    --output-dir $RANDOM_DIRNAME > $RANDOM_DIRNAME/result.json || {
    rm -rf ${RANDOM_DIRNAME}
    exit 1
}
