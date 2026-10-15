#!/bin/zsh
# usage: run_device.sh DEVICE [modes...]; runs modes sequentially, 6 ngspice workers
dev=$1; shift
for m in "$@"; do
  python3 -I $(cd "$(dirname "$0")" && pwd)/harness.py $m --device $dev --workers 8 || echo "FAIL $dev $m"
done
echo "DONE $dev $*"
