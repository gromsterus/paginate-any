#!/bin/bash

printf_center() {
  maxwidth="${2:-60}"
  termwidth="$(tput cols)"
  if [[ $termwidth -gt $maxwidth ]]; then
    termwidth=$maxwidth
  fi
  padding="$(printf '%0.1s' ={1..500})"
  printf '%*.*s %s %*.*s\n' 0 "$(((termwidth-2-${#1})/2))" "$padding" "$1" 0 "$(((termwidth-1-${#1})/2))" "$padding"
}

err=0
trap 'err=1' ERR
FIX=${1}

if [[ $FIX == "--fix" ]]; then
    ruff_flags="--fix"
    black_flags=""
elif [[ $FIX == "" ]]; then
    ruff_flags=""
    black_flags="--check"
else
    echo "Unknown argument: $FIX"
    exit 1
fi

printf_center "Ruff" && ruff check $ruff_flags src tests
printf_center "Black" && black $black_flags src tests
printf_center "MyPy" && mypy --install-types --non-interactive src tests

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color
printf_center "Result"
if [[ $err == 0 ]]; then
    echo -e "${GREEN}All checks passed!${NC}"
else
    echo -e "${RED}Something went wrong.${NC}"
fi
exit $err
