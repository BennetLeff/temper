#!/bin/sh
# sensitivity sweeps for proposals (uniform-h airflow bound, tank-current derate); 0.5 mm converged-model + 1 mm legacy (scorecard metric)
cd "$(dirname "$0")"
for h in 25 30 35 45; do
  python3 -I b3_rerun.py --scenario base --op c28 --h $h --pitch 0.5 >/dev/null 2>&1 &
  python3 -I b3_rerun.py --scenario base --op c28 --h $h --pitch 1.0 --config legacy >/dev/null 2>&1 &
  wait
done
for it in 22 24 26 27 28; do
  python3 -I b3_rerun.py --scenario base --op c28 --h 25 --pitch 0.5 --it $it >/dev/null 2>&1 &
  python3 -I b3_rerun.py --scenario base --op c28 --h 25 --pitch 1.0 --config legacy --it $it >/dev/null 2>&1 &
  wait
done
