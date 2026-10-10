#!/bin/sh
# Stage 15b: reproduce every number in PLAN-15b.md. Needs KiCad 10.0.4 (pcbnew Python, kicad-cli),
# python3 with numpy / scipy / shapely / matplotlib, and the committed unit at $U (read only).
#   sh run_all.sh
set -e
S=$(cd "$(dirname "$0")" && pwd)
cd "$S"
# 0. inputs: model/ is a copy of round5-native21 (thermal.py, run_study.py, run_board.py, run_cases.py, A4 outputs,
#    power_copper.json.gz) and native21s15-all-copper.json.gz; kicad/base/ is the routed stage-15 board 5b9dbd61.
python3 model/b3/thermal.py --selftest > /dev/null
# 1. cause: per-source superposition, heat bins, lead-path bias on the committed copper
python3 diag_decompose.py
python3 heatmap_cases.py
python3 lead_bias.py
# 2-3. candidates: KiCad edit + refill + DRC + export + 14 A4 cases + B3 c28 (committed thermal.py)
for n in c0_refill c1_f_corner c1b_fb_corner c2a_link_q3 c2b_link_all c2c_link_all1 c2f_link_e1 c2g_link_q3_15 c2h_link_e1_notie; do
  sh run_candidate.sh $n
done
python3 region_check.py c0_refill c1_f_corner c1b_fb_corner c2a_link_q3 c2b_link_all c2c_link_all1 c2f_link_e1 c2g_link_q3_15 c2h_link_e1_notie
python3 cut_widths.py kicad/c0_refill/all-copper.json.gz kicad/c1_f_corner/all-copper.json.gz kicad/c2h_link_e1_notie/all-copper.json.gz kicad/c2f_link_e1/all-copper.json.gz
python3 area_delta.py kicad/c0_refill/all-copper.json.gz kicad/c2h_link_e1_notie/all-copper.json.gz
# stray-heat fix (thermal_snap.py), mesh study, and the recommended fix's attribution / lead bias
python3 snap_screen.py c0_refill c1_f_corner c2a_link_q3 c2c_link_all1 c2f_link_e1 c2g_link_q3_15 c2h_link_e1_notie
python3 mesh_study.py c2h_link_e1_notie
K=kicad/c2h_link_e1_notie
A4_COPPER=$S/$K/power_copper.json.gz python3 diag_decompose.py $K/all-copper.json.gz a4/c2h_link_e1_notie c2h
python3 lead_bias.py c2h $K/all-copper.json.gz a4/c2h_link_e1_notie $K/power_copper.json.gz
python3 b3_eval.py c2h_link_e1_notie $K/all-copper.json.gz a4/c2h_link_e1_notie $K/power_copper.json.gz "1.0 0.5"
python3 lead_core.py c0_refill c2h_link_e1_notie
