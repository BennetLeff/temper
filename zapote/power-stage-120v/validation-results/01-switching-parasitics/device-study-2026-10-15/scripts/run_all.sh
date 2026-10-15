#!/bin/zsh
# full simulation chain for the study (sequential; 8 ngspice workers)
S=$(cd "$(dirname "$0")" && pwd)
$S/run_device.sh IPW65R018CFD7_L1 repro
$S/run_device.sh IPW65R018CFD7_L1 energy
$S/run_device.sh IPW65R029CFD7_L1 energy
$S/run_device.sh IPW65R018CFD7_L1 edge
$S/run_device.sh IPW65R029CFD7_L1 edge
$S/run_device.sh IPW65R018CFD7_L1 zvs
$S/run_device.sh IPW65R029CFD7_L1 zvs
echo ALLDONE
