#!/bin/bash

err=0
trap 'err=1' ERR

ruff check .
black --check .
mypy --install-types --non-interactive src tests

exit $err
