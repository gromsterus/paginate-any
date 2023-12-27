#!/bin/bash

set -o errexit
set -o nounset

cov_report=${1:-html}
exec python -m pytest --cov-report "$cov_report" --cov-report term --cov=src
