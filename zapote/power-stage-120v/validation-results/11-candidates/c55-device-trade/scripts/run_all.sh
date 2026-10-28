#!/bin/zsh
# c55 simulation chain, in priority order (sequential; W ngspice workers, default 8). Existing results.json are kept,
# so the chain resumes where it stopped. Prerequisite: the vendor files in $C55_DL (README, Datasheets and models).
#   python3 -I c00_controls.py && python3 -I c05_qrr.py      (controls and diode-charge calibration, first)
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-8} || echo "FAIL $1 $2"; }
# --- controls that run on the trade harness: B3 gate-charge basis (382.6 nC) and the S6 maximum-Qrr 68.16 V/ns
run s2q cfd7_c39__q
run full cfd7_c39_tt260
# --- CM8, Infineon 650 V vendor model; TT 100 / 180 ns = datasheet typical / maximum Qrr (c05_qrr.py)
for c in cm8_r27_tt180 cm8_r39_tt180 cm8_r47_tt180 cm8_r68c4p7_tt180 cm8_r39 cm8_r39_tt100; do run s4b $c; done
for c in cm8_r39 cm8_r39_tt100 cm8_r39_tt180 cm8_r68c4p7_tt100 cm8_r68c4p7_tt180; do run full $c; done
run s2q cm8_r39__q
# --- loss grids (long window): CFD7 on the s42 network (baseline), CFD7 8.2 ohm (measure control, c50 C3);
#     the CM8's loss grid is on its selected network (run_cm8_sel.sh)
for c in cfd7_c39 cfd7_8p2; do run energy $c; done
# --- SiC: IMW65R026M2H at the board's +15 / -1.6 V rails (full grid) and at +18 / -1.6 V (binding S4 set; the rail
#     changes the gate drive only); loss grids at both
run s4b sic26_15_r8p2; run full sic26_15_r8p2
run s4b sic26_18_r8p2
run eA sic26_15_r8p2; run eA sic26_18_r8p2
run s2q sic26_15_r8p2__q; run s2q sic26_18_r8p2__q
# --- RC-IGBT (35-60 kHz drop-in): loss on leg A, short window (the model is ~20x slower than the CoolMOS ones);
#     S4 binding set and S2 rows for R6 (a 640-run grid would take ~2 h and adds nothing to the loss verdict)
for c in rch6_r8p2 rch5_r8p2; do run eAs $c; done
run s2q rch6_r8p2__q
# (s4b rch6_r8p2 was started and stopped: the first 19 S4 rows all aborted at the RC diode's recovery, 'timestep too small' in the
#  model's diode d1xuj, as in the c05 recovery fixture; the 0.1 ns retries run into the 30 min ngspice timeout)
echo ALL_DONE
