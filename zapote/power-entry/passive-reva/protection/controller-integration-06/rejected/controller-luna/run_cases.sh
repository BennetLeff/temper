#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$here"
rm -f controller_functional.log controller_pcl_negative.log controller_standby_negative.log integrated_closed_loop.log
ngspice -b -o controller_functional.log controller_functional.cir
ngspice -b -o controller_pcl_negative.log controller_pcl_negative.cir
ngspice -b -o controller_standby_negative.log controller_standby_negative.cir
ngspice -b -o integrated_closed_loop.log integrated_closed_loop.cir
rustc --edition=2021 checks.rs -O -o .checks
./.checks controller_functional.log controller_pcl_negative.log controller_standby_negative.log integrated_closed_loop.log
