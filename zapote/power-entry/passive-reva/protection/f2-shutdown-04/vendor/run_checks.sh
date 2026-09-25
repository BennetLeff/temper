#!/bin/sh
set -eu
cd "$(dirname "$0")"
for name in driver-final-interface startup-fast startup-ramp; do
  ngspice -b -o "$name.log" "$name.cir"
done
rustc --edition=2021 check_driver.rs -o /tmp/f2b-check-driver
/tmp/f2b-check-driver driver-final-interface.log startup-fast.log startup-ramp.log > checks.txt
rustc --edition=2021 --test check_driver.rs -o /tmp/f2b-driver-tests
/tmp/f2b-driver-tests > tests.txt
