# Reproduce D-28

Use base `6717013f7ffcd7f880dc750a0579ef89059c480f` plus this output directory. Run from `out-D28/`. The recorded host uses ngspice 45.2 at `/opt/homebrew/bin/ngspice`, rustc 1.92.0, and `/Users/bennet/Miniforge3/bin/python3` with NumPy and matplotlib. These paths are transport defaults, not part of the circuit. `result.json` pins the simulator executable and every physical-input hash; substituting a simulator requires a fresh campaign directory. Never reuse an existing result whose identity differs.

```sh
export PYTHONDONTWRITEBYTECODE=1
bash fetch_models.sh
rustc --edition=2021 -O physics.rs -o physics
rustc --edition=2021 --test physics.rs -o physics-tests
./physics-tests
./physics ideal > ideal.csv
python3 ideal_oracle.py
./physics oracle ideal-oracle-v2.csv
python3 plot.py
python3 run.py complementary.json --workers 2
python3 run.py refinement.json --workers 2
python3 run.py quarter-step.json --workers 2
python3 run.py boundary.json --workers 2
python3 run.py upper-boundary.json --workers 2
python3 run.py candidate-refinement.json --workers 1
python3 replay.py
python3 qualification_campaign.py
python3 summarize.py
python3 report.py
python3 plot_waveforms.py
python3 verify.py
```

Use a Python interpreter with the dependencies above. `ideal_oracle.py` regenerates `ideal-oracle-v2.csv`, transporting the oracle’s six `R,phase,ia,ib,irms` rows before invoking Rust. Device campaigns can take hours; each solver invocation is bounded at 1800 monotonic seconds. Existing `result.json` files are immutable run-cache records, including indeterminate attempts. Reproduce in a fresh copy/output directory to execute again; do not delete failed history to turn a retry into the original run.

`campaign.json` and `run-startup-attempt.py` retain the initial startup adaptation. Its unstarted cases were withdrawn when the complementary startup was selected; the attempted subset is retained under `runs/v…`. The original anchor attempt was interrupted and retained; `anchor-original-170-35k-repeat` is the completed matching-condition reproduction. The final analysis reads `runs/*/replay/analysis.json`; the original run records preserve the analysis version used when each solver finished.

The licensed library and archive stay under ignored `vendor/`, and each run's library link is ignored. Only simulation outputs and source decks that reference the external library belong in Git. Source-model bytes are never embedded in the deck. The fetcher verifies full archive and extracted-library hashes before any run.

`qualification_campaign.py` forwards adjacent completed timestep pairs to D-22's comparator. Incomplete pairs remain indeterminate. `verify.py` checks every terminal attempt, raw/deck/options/parameter identities, final-analyzer identity, unchanged FFT replay, declared campaign coverage, the exact D-22 anchor and the independent ideal oracle. Import-boundary and report-only derived-artifact checks are separately recorded in `repo-gates.json`; no Rust workspace/native bridge build is needed.
