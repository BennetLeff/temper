# B3 ratings: model refinement (2026-10-15, DECISIONS 51)

Analysis study, run in a scratch folder against frozen git extracts. s38 is pinned at f8cca7d21 and s35 at c36251e41.
This folder keeps what the record needs:
- `results-s38/` is the record (s38); `results/` is the same set for s35. Margins agree to 0.1 K between the two.
- `TABLES.md` and `summary.json`: margins before and after each correction.
- `targets.json`: fix targets and ceilings.
- `heat-corrections.json`, `sink_model.json`, `laminate_scope.json`, `a4_fields.json`, `e2e.json`, `confirm-*.json`.
- `patches/`: the four diffs, applied to the repo in the DECISIONS 51 commit:
  - `lead-path.diff`: thermal_body.py and body_runs.py, the FET drain-lead path to the sink;
  - `heat-c28-60khz.diff`: make_heat_sources.py, c28 rows at 60 kHz with Q_DECK 382.6 nC;
  - `gate-proposed-rows.diff`: b3_ratings_gate.py, film caps C38–C41 and the gate resistors gated;
  - `run-basis-lead.diff`: run_basis.py with the lead path, plus fet_case.py.
- `scripts/` and `run_all.sh`: the study's own scripts. They read the scratch frozen tree (absolute paths) and are kept as
  a record.

**Reproduce from the repo:**
```
cd ../../b3 && python3 make_heat_sources.py
cd ../b3-ratings && python3 run_basis.py
```
This needs the task-04 `-heat.npz` fields of the same board in `../outputs/`; they are gitignored. On s38 it gives
laminate −38.0 K and rated parts −63.9 K (worst: R12 1206 terminal derating), identical to `results-s38/e2e.json`.
The integration session reproduced this.

Not committed: `dl/` (datasheets), `frozen/`, `work/`, `runs*/` (~1.9 GB of solves).
