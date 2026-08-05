# Scripts

Utility scripts for the Temper induction cooker project.

## ci_check_drc.py

The CI DRC ratchet uses real `kicad-cli pcb drc` by default. It is a blocking
truth gate on the Linux regression runner; the Rust engine remains available
only as an explicit diagnostic backend:

```bash
uv run python scripts/ci_check_drc.py                 # KiCad truth gate
uv run python scripts/ci_check_drc.py --backend rust  # diagnostic only
```

If KiCad cannot execute or return a report, the command fails as
**unmeasured**. It never treats a CLI crash as zero violations.

## placement_quality_report.py — RETIRED (2026-08-04)

**This script no longer exists.** It was RETIREd as import-dead and deleted on
2026-08-04: its module-level imports of `temper_placer.losses.base` and
`temper_placer.routing.analysis` had not been resolvable since those JAX-era
packages were retired, so it could not be run at all. The verdict and full
justification are in `docs/evidence/2026-08-04-wave4-residual-verdicts.md`.

The roughly 125 lines of usage, output-format, and workflow-integration
documentation that stood here described an interface no reachable code
provided, and are removed rather than left as instructions a reader would
follow into a `ModuleNotFoundError`. They remain in git history if the metric
definitions are ever wanted. Two things that section referenced were already
gone independently: `scripts/test_placement_quality_report.py` (no such file)
and the `bd-done` GPBM integration it proposed (never wired up).

No replacement exists. Placement quality metrics live in
`temper_placer.metrics.quality`; the DRC path is `make drc` /
`scripts/ci_check_drc.py`. Rebuilding a unified CLI report on top of those is
unclaimed work, not an existing capability.
