---
title: "Design-rules oracle PD3 creepage re-pin"
date: 2026-08-27
status: prepared-for-separate-landing
module: temper-placer
topic: oracle-repin
provenance:
  base_commit: c24d0381044e6c77621d18a7616b5e945bb4419b
  landing_commit: UNKNOWN
  dirty: true
---

<!-- provenance: commit=c24d0381044e6c77621d18a7616b5e945bb4419b dirty=true -->

# Design-rules oracle re-pin: `HighVoltageTank` 6.3mm → 10.0mm

This record prepares the existing `_design_rules_py_oracle.py` re-pin for a
separate, deliberate landing commit. No landing commit exists yet; the
provenance above names only the existing base commit and records the dirty
working-tree state.

## Why the pin changes

The old oracle value, `HighVoltageTank.creepage_mm = 6.3`, was the conditional
PD2 functional-insulation value. The as-built board has no sealed compartment,
so the documented decision is PD3. For the measured 570.5 Vrms tank swing,
IEC 60335-1 Table 18, band `>500–800 V`, material group IIIa/IIIb, gives
6.3mm at PD2 and **10.0mm at PD3**. The authoritative determination is
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` (Table 18 and its
PD3 conclusion), with the pollution-degree decision in
`docs/evidence/2026-08-11-pd2-decision-record.md`.

The current implementation chain agrees on 10.0mm:

- `scripts/generate_kicad_dru.py` looks up Table 18 and selects `PD3` for
  `HV_TANK_CREEPAGE_ENFORCED_MM`.
- `packages/temper-placer/configs/netclass_rules.yaml` sets
  `HighVoltageTank.creepage_mm: 10.0`.
- `packages/temper-placer/configs/pair_creepage.generated.yaml` emits
  `HighVoltage|HighVoltageTank` and `HighVoltageTank|HighVoltageTank` as
  `10.0`.
- `packages/temper-placer/src/temper_placer/core/design_rules.py` and
  `placer/cp_sat/tank_creepage.py` use the same PD3 contract; the latter keeps
  6.3mm as the explicit PD2 fallback constant.

## Exact diff scope

The semantic re-pin is one literal in
`packages/temper-placer/tests/core/_design_rules_py_oracle.py`:

```diff
-creepage_mm=6.3,
+creepage_mm=10.0,
```

The oracle’s module comment was extended to explain this re-pin and correct
the source citation. `scripts/oracle_hashes.json` updates only the digest for
that oracle. No callable behavior, net assignment, Rust implementation, or
generated pair-table value is introduced by this re-pin; those are the source
contract being checked. The original PD2 value remains represented by the
live tank constants and their evidence.

## Gates run

- `uv run python scripts/check_oracle_hashes.py` — **passed** (159/159).
- `python3 -m py_compile` on the affected Python files — **passed**.
- `uv run pytest -q scripts/tests/test_route_board_report.py` — **passed** (1
  test).
- `git diff --check` — **passed**.

The full placer differential suite was not claimed here: this checkout’s
installed `temper_io_types` extension is stale and lacks `write_types`, so
collection stops before tests run. Rebuild extensions and run the focused
design-rules differential tests when the separate landing commit is prepared.
