#!/bin/bash

set -o errexit
set -o nounset

exec python -m pytest --cov-report html --cov-report term --cov=.
