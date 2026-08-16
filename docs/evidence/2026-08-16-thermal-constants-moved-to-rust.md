# Thermal constants moved to Rust — 2026-08-16

## Summary

The thermal design constants previously defined in the Python module
`temper_placer/physics/thermal.py` now live in the `temper-thermal` Rust
crate (`packages/temper-thermal/src/thermal_constants.rs`) — the same
crate as the thermal kernels that consume them. `physics/thermal.py` is
now a thin re-export shim that reads the constants back from Rust at
import time and holds **no copy** of any thermal value.

This closes the "one fact, many homes" instance (handoff §2 mechanism 1)
where the constants lived in Python and reached the Rust kernels only as
marshalled argument arrays — the Rust crate had zero copies, but the
values' only home was outside the crate that does the analysis.

## What moved (verbatim — no value was invented or reconstructed)

| Constant | Value | Provenance (unchanged from the Python SSOT) |
|---|---|---|
| `DEFAULT_AMBIENT_C` | 60.0 °C | `docs/ENVIRONMENTAL_SPEC.md` §1.1 derating zero-power point; decision doc `docs/evidence/2026-08-15-thermal-threshold-decision.md` §6.4 |
| `FIRMWARE_TRIP_TS_C` | 80.0 °C | firmware over-temp trip at the heatsink sensor (NTC_HS); decision doc §6.1 ladder (75 warn / 80 firmware / 85 latch) |
| `T_J_DESIGN_MAX_C` | 125.0 °C | datasheet-recovery design-for junction limit (decision doc §6.1) |
| `T_J_ABS_MAX_C` | 175.0 °C | IKW40N120H3 Tvj(max) — NOT Tstg = 150 °C, the storage temp the pre-correction analysis wrongly used |
| `IKW40N120H3_RJC_KW` | 0.31 K/W | `components/IKW40N120H3/IKW40N120H3_Documentation.md` §1.2 |
| `TIM_RCH_KW` | 0.20 K/W | committed TIM/Sil-Pad figure, `docs/guides/THERMAL_DESIGN_GUIDE.md` §3.1 |
| `HS1_RHA_KW` | 0.45 K/W | HS1 Wakefield-Vette 392-120AB with fan (same source) |
| `TO220_RJC_PLACEHOLDER_KW` | 0.60 K/W | TO-220-class placeholder — no recovered datasheet |
| `PLACEHOLDER_RJC_RCH_RHA` | (0.6, 0.25, 1.0) K/W | legacy flat stand-ins, kept unchanged |

Per-device stackups (identical to the pre-move table):

- IKW40N120H3 IGBTs (legacy refs Q1/Q2; current-board U4/U5; cross-branch
  U6): **(0.31, 0.20, 0.45)** K/W — datasheet Rjc, committed TIM Rch,
  HS1-with-fan Rha.
- TO-220 rectifiers on the shared HS1 heatsink (U1/U2): **(0.60, 0.20,
  0.45)** K/W — TO-220-class Rjc is a **placeholder — no recovered
  datasheet**; Rch/Rha are the committed shared-heatsink figures.
- Every other device: **(0.6, 0.25, 1.0)** K/W flat legacy placeholder.

## Design decisions

### 1. Resistance table keyed by device identity, not refdes

Per handoff §6 ("designators are not stable across branches"): the
resistance table is keyed by the device's **stable identity** — value
string first (`"IKW40N120H3"`), then footprint class
(`Package_TO_SOT_THT:TO-247-3_Vertical` / `TO-220-2_Vertical`), then the
placeholder. `thermal_resistance_for(refdes)` keeps the refdes-based API
the analysis calls, but the refdes → identity map is a small, explicit,
per-entry-documented compatibility layer; the resistance VALUES are
attached to the device, never to the designator.

### 2. Shim, not deletion

`physics/thermal.py` was reduced to a shim rather than deleted because
`estimate_junction_temp` is a public API with default arguments used by
four consumers (production `thermal_potential.py` plus three test
files), and the repo's established migration pattern (AGENTS.md, handoff
§1) is "pure-delegation shim with a Rust owner". The shim reads all
constants from Rust at import time (`_tt.default_ambient_c()` etc.), so
the "one fact, many homes" problem is gone — there is exactly one home.

### 3. Pinned oracle NOT re-pinned — deliberately

`tests/metrics/_physics_py_oracle.py` is byte-identical before and after
this change: it imports `thermal_resistance_for` from the shim, whose
name and semantics are unchanged, and whose values are identical. Its
content hash in `scripts/oracle_hashes.json` therefore did not move, and
the oracle gate verifies 167/167 files byte-identical. Re-pinning would
have been a gratuitous edit to a VERBATIM pin ("DO NOT EDIT EXCEPT FOR A
DELIBERATE, DOCUMENTED RE-PIN"); the oracle still pins what it pinned —
the Rust kernel's arithmetic against the Python reference chain, given
per-device resistances — and the differential suite re-verified it.

## Verification

- **Rust**: `cargo test` in `packages/temper-thermal` — **2756 passed,
  0 failed**. The 4 new `thermal_constants` tests pin every constant to
  its pre-move Python value and every refdes lookup to the pre-move
  `THERMAL_RESISTANCE_BY_REF` table (all 7 entries + fallback).
- **Python**: `pytest tests/physics/ tests/metrics/` — **1862 passed**,
  including `test_thermal_rust_differential.py` (module-level delegation
  pins + bit-exact kernel pins), `test_physics_rust_differential.py`
  (oracle-vs-kernel bit-exactness, 169 tests in the two differential
  files), `test_thermal.py`, `test_thermal_potential.py`.
- **PBT**: `test_thermal_rust_pbt.py`, `test_thermal_potential_rust_pbt.py`,
  `test_thermal_potential_rust_differential.py` — **159 passed**.
- **Thermal analysis identical**: `docs/evidence/2026-08-15-thermal-analysis-run.py`
  (the real-board sensor-chain analysis) produces byte-identical output —
  same ambient 60 °C, same limits 80/125/175 °C, same per-device
  Rjc/Rch/Rha (U4/U5 0.31/0.20/0.45, U1/U2 0.60/0.20/0.45), same Ts/Tc/Tj
  and margins.
- **pyo3 registration**: `scripts/check_pyo3_duplicate_registration.py` —
  0 duplicates (the lib.rs registrations are all unique names; the
  pyo3-shadowing hazard from AGENTS.md does not apply).
- **Import linter**: `import_linter_gate.py` — PASSED, 0 new violations.
- **Oracle hashes**: `check_oracle_hashes.py` — 167/167 OK (unchanged).
- **Wasm registry**: `gen_wasm_test_registry.py --crate temper-thermal
  --check` — up to date (2701 tests across 19 modules; the new
  `thermal_constants` test module is registered and wasm-compatible —
  pure Rust, no pyo3 gate).

## Pre-existing failures NOT caused by this change (verified)

- `tests/validation/test_thermal_battery_run.py`: 6 failures, all
  `ngspice not available` — the battery-run harness requires ngspice for
  its independent operating-point cross-check; ngspice is not installed
  on this machine. Unrelated to this change.
- `make regen-check`: 3 pre-existing issues, each confirmed to have zero
  diff vs `origin/main` on the flagged files: 2 `NEW_SITE` hash-order
  defects (`cli/repair_commands.py`, `router_v6/trace_width_assignment.py`),
  3 manifest-less scripts, and 4 `NEW_UNWIRED` kernels in
  `temper-geometry/src/layer_identity.rs`.

## Not changed

- `pcb/temper.kicad_pcb` — untouched (sha256 verified before/after).
- No check weakened, no ratchet ceiling moved, no standards value
  invented or reconstructed.
- Firmware trip constants (`firmware/config.yaml`) are the firmware's own
  enforcement point — out of scope for this move (the 80 °C firmware
  trip cross-checks against `FIRMWARE_TRIP_TS_C`; a follow-up could
  single-source that too, but it is a separate system boundary).
