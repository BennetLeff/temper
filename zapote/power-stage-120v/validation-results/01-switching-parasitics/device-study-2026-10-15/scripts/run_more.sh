#!/bin/zsh
S=$(cd "$(dirname "$0")" && pwd)
until grep -q ALLDONE $(cd "$(dirname "$0")/../sims" && pwd)/log_all.txt; do sleep 20; done
$S/run_device.sh IPW65R018CFD7_L1 edge2
$S/run_device.sh IPW65R029CFD7_L1 edge2
$S/run_device.sh IPW65R041CFD7_L1 energy
$S/run_device.sh IPW65R029CFD7_L1 cm8rg cm8rg2
echo MOREDONE
