# D-18 verification

Python 3.12, 2026-10-02. No SPICE, Rust, native bridge or firmware build.

- `PYTHONDONTWRITEBYTECODE=1 python3.12 .../out-D18/losses.py`: 90 cases, 62 below the inherited static CT-min screen; complete selected D15/D13 inputs and matching native17 identities/positions.
- `python3.12 -m unittest discover -s .../out-D18 -p test_losses.py`: 4 passed. Independent closed-form common-sink solution, zero-power network, infeasible interface handling, datasheet reference points.
- Import gate with `UV_PROJECT_ENVIRONMENT=/tmp/d11-validation-venv`, `UV_CACHE_DIR=/tmp/d18-uv-cache`, `PYTHONPATH=packages/temper-placer/src`: 5 contracts kept, 0 broken. The first sandbox run could not access uv's cache; it was a tool error, not a pass.
- Review performed sequentially in the main context as required by AGENTS.md. Checked thermal equations against a closed-form network, power partition, complete-cycle scaling, diode double-counting, selected-input completeness, source provenance and scope. No independent model review is claimed. Reuse/quality/efficiency review retained the local arithmetic script: the old script depends on absent switching events and uses superseded assumptions. No production abstraction or dependency was introduced.
- Review corrected the no-feasible-sink branch to handle a divergent ideal-sink calculation, preserved the original per-mechanism record schema, and added all-candidate bridge sensitivities. All actionable local findings were addressed.

Physical coverage remains conditional: no hot maximum RDS(on), measured switching histogram, installed cooling curve, interface qualification or enclosure test. Read the report before using the allocation.

- Second replay: JSON and CSV SHA-256 unchanged. `scripts/regen_derived.py --check`: all derived artifacts consistent. Read-only check used to respect the output-folder-only scope.
