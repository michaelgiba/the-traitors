#!/bin/bash

set -euo pipefail

PARENT_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"

source ${PARENT_DIR}/.venv/bin/activate

set -x

mkdir -p ${PARENT_DIR}/analysis/traitors

python -m reality_show_bench.analyze_results \
    --input-results-dir ${PARENT_DIR}/results/traitors \
    --output-dir ${PARENT_DIR}/analysis/traitors
