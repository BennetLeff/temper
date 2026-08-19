<!-- provenance: commit=2b18ade3e branch=fix/thermal-corrections-v2 dirty=false (the code-fix commit the analysis was run against; the analysis-run script and this doc were committed on top) -->

# Thermal analysis corrections implemented — ambient 60 °C, margin vs 80 °C firmware trip, per-component Rjc/Rch/Rha (2026-08-15)

**Branch:** `fix/thermal-corrections-v2` (base `origin/main`)
**Targets supplied by:** `docs/evidence/2026-08-15-thermal-threshold-decision.md`
(§6.4 "What the thermal analysis should use as design limits"; §7 file list).

This document records what the thermal-analysis correction changed, the
measured results on the current board, and what was deliberately NOT
changed (with reasons). It is the companion to the decision doc: that
document decided the hierarchy, this one implemented it in the analysis
code.

---

## 1. The corrections

### 1.1 Ambient: 40 → 60 °C

Every thermal-analysis default that used 40 °C now uses **60 °C** — the
design-limit ambient (zero-power point of `docs/ENVIRONMENTAL_SPEC.md` §1.1's
derating curve: 100 % at 40 °C → 0 % at 60 °C). Sites changed:

- `physics/thermal.py` — `DEFAULT_AMBIENT_C = 60.0`; `estimate_junction_temp`
  default `ambient_C=60.0`.
- `metrics/physics.py::measure_thermal` — `ambient_temp_c=60.0`.
- `physics/thermal_potential.py::validate_tj_safety` — `ambient_C=60.0`.
- `physics/operating_point.py::OperatingPointConfig.T_amb` — 40.0 → 60.0.
- `physics/parameter_bounds.py` — corner ambient fallback 40.0 → 60.0.
- `physics/thermal_fdm.py::ThermalFDMConfig.ambient_C` — 40.0 → 60.0.
- `physics/copper_coverage.py::check_thermal_plausibility` ambient default
  (accepted-and-ignored param) 40.0 → 60.0 for intent coherence.
- `validation/mfem_gate.py`, `validation/results/battery_run.py` — ambient 60.0.
- `physics/tj_cross_check.py::TjCrossCheckGate.T_amb` — 40.0 → 60.0.
- `temper-design-bundle/src/specification_contracts.rs::ThermalSpec` —
  `ambient_temp_c` default 40.0 → 60.0.
- `packages/temper-placer/configs/pcb_spec.yaml` — `ambient_temp_c: 60.0`.

### 1.2 Margin basis: 150 °C (storage temp) retired; 80 °C firmware trip + 125/175 °C junction limits

The 150 °C that served as the analysis margin basis had **no datasheet
basis as a junction limit** — the IKW40N120H3 gives Tvj(max) = **175 °C**;
150 °C is the datasheet's **storage** temperature (Tstg = −55…+150 °C),
per the decision doc §1.5. The corrected hierarchy (decision doc §6.1, §6.4):

| Limit | Value | Home |
|---|---|---|
| Firmware over-temp trip (heatsink sensor, Ts) | **80 °C** | `physics/thermal.FIRMWARE_TRIP_TS_C` — the first active protection layer |
| Hardware latch (heatsink sensor, Ts) | 85 °C | THM-01 (unchanged, governing) |
| Junction design-for | **125 °C** | `physics/thermal.T_J_DESIGN_MAX_C` — datasheet-recovery §5.1.1 "design for ≤125 °C" |
| Junction absolute survival | **175 °C** | `physics/thermal.T_J_ABS_MAX_C` — Tvj(max) |

`measure_thermal`'s `thermal_margin_c` is now **the margin of the hottest
heatsink temperature against the 80 °C firmware trip, in sensor space**
(`80.0 - max_ts`), because the sensor measures Ts, not Tj. The 125/175 °C
junction limits are reported alongside `max_junction_temp_c`. This
satisfies both the correction brief ("replace 150 with the firmware trip")
and the decision doc's §6.4 ("the *design* margin should be reported
against 125/175 °C junction, with the 80 °C sensor trip as the
hardware-realized bound") — the firmware-trip margin is the
protection-ladder margin, and the junction limits are the physics limits.

Other 150 °C sites re-pointed to 175 °C (survival — these are absolute-max
gates): `operating_point.py` `T_j_max`, `parameter_bounds.py` `T_j_max`,
`battery_run.py` `T_j_max` (×3), `elec/src/constraints.ato`
`igbt_max_temp` 423.15 K → 448.15 K. `igbt_derate_temp` (398.15 K = 125 °C)
was already correct as the derate figure. `pcb_spec.yaml` /
`ThermalSpec` `max_junction_temp_c` 110 → **125 °C** (design-for; 110 had no
documented basis).

### 1.3 Per-component thermal resistances (was flat 0.6 / 0.25 / 1.0 for everything)

The `measure_thermal_edges` kernel (`packages/temper-thermal/src/thermal_edges.rs`)
now takes **per-device Rjc/Rch/Rha** arrays and computes the explicit sensor
chain per device:

```
Tj = Tc + P·Rjc        (junction → case)
Tc = Ts + P·Rch        (case → heatsink, through TIM/isolator pad)
Ts = Ta + P·Rha        (heatsink → ambient, with fan)
```

It returns `(max_tj, max_ts, edge_avg)` — `max_ts` is what the firmware
trip margin is anchored to. Values are resolved by
`physics/thermal.thermal_resistance_for(ref)`:

| Device | Rjc (K/W) | Rch (K/W) | Rha (K/W) | Source |
|---|---|---|---|---|
| IKW40N120H3 IGBT (Q1/Q2 legacy, U4/U5 current board) | **0.31** | 0.20 | 0.45 | Rjc: datasheet recovery §1.2 (`components/IKW40N120H3/IKW40N120H3_Documentation.md` lines 78-79); Rch: committed TIM/Sil-Pad figure (`docs/guides/THERMAL_DESIGN_GUIDE.md` §3.1); Rha: HS1 Wakefield-Vette 392-120AB with fan (same source; decision doc §3.2 commits 0.45) |
| TO-220 rectifiers on HS1 (U1/U2) | 0.60 **placeholder** | 0.20 | 0.45 | Rjc: TO-220 package-class placeholder — **no recovered datasheet**; Rch/Rha: shared HS1 figures |
| Everything else | 0.60 | 0.25 | 1.0 | **Placeholder** — the legacy flat stand-ins, kept with an explicit "not measured" comment |

`estimate_junction_temp`'s defaults became the IGBT datasheet values
(0.31 / 0.20 / 0.45) with citations; the generic package lookup
(`infer_rjc`, TO-247 → 0.6) is **unchanged** — it is a generic
package-class table for arbitrary parts, not the IKW40N120H3's per-part
value, and it is three-way mirrored (see below).

---

## 2. Measured results on the current board

Run: `docs/evidence/2026-08-15-thermal-analysis-run.py` (parses
`pcb/temper.kicad_pcb`; no files modified). Design-limit ambient 60 °C,
20 W per IGBT (conservative end of the committed 18-20 W), 5 W placeholder
for the TO-220 rectifiers (their loss is not recorded in-repo — flagged,
not invented).

```
ref     P(W)    Rjc    Rch    Rha |      Ts     Tc     Tj |  m_Ts  m_Tj125 m_Tj175  verdict
U4      20.0   0.31   0.20   0.45 |    69.0   73.0   79.2 |  11.0   45.8   95.8  OK
U5      20.0   0.31   0.20   0.45 |    69.0   73.0   79.2 |  11.0   45.8   95.8  OK
U1       5.0   0.60   0.20   0.45 |    62.2   63.2   66.2 |  17.8   58.8  108.8  OK
U2       5.0   0.60   0.20   0.45 |    62.2   63.2   66.2 |  17.8   58.8  108.8  OK
```

- The IGBT rows reproduce the decision doc §3.3 design-limit row (69 / 73 /
  79.2 °C) **exactly** — independent confirmation that the corrected chain
  and the decision doc agree.
- **No device fails margin at the 60 °C design-limit ambient.** The IGBTs
  sit 11 °C below the 80 °C firmware trip, 45.8 °C below the 125 °C
  design-for junction, 95.8 °C below the 175 °C survival limit — matching
  the decision doc's conclusion that the IGBT is not the binding
  constraint anywhere in the protection family.
- **Fault sensitivity (2× nominal loss, 40 W/IGBT):** U4/U5 → Ts = 78.0 °C
  (still under the 80 °C firmware trip), Tc = 86.0 °C, Tj = 98.4 °C,
  survival margin 76.6 °C. The decision doc's §3.3 fault row (Ts = 85 at
  the hardware latch, 2× loss → Tj = 105.4 °C) remains the upper bound.

**Honest reds:** none at the design-limit ambient — the corrections make
the analysis *less* alarmist than the flat 0.6/0.25/1.0 + 150 °C model was,
and this is the correct physics, not a weakening: the old model's "margins"
were measured against a storage-temperature number with flat stand-in
resistances. The reds that DO exist are the known, documented hardware
defects (IGBT rotation/edge-distance mismatch, THM-01 lead-reach open
item — see `docs/evidence/2026-08-12-thermal-constraint-derivation.md`),
none of which this change touches.

---

## 3. Deliberate re-pins (behaviour change, oracles re-pinned in the same commit)

Per the repo rule, changing a pinned oracle is a deliberate act, recorded
here:

- `tests/metrics/_physics_py_oracle.py::_oracle_measure_thermal` — re-pinned
  to the corrected model (per-device R, Ts→Tc→Tj chain, 60 °C ambient,
  `80.0 - max_ts` margin). Content hash re-pinned in
  `scripts/oracle_hashes.json` (e305db33… → b0325840…).
- `tests/physics/test_thermal_rust_differential.py::_oracle_estimate_junction_temp`
  defaults — re-pinned to the corrected module defaults (60 / 0.31 / 0.20 /
  0.45). The arithmetic body is unchanged; the kernel pins remain
  bit-exact against the same arithmetic.
- `tests/core/_specification_py_oracle.py::_OracleThermalSpec` defaults —
  re-pinned to 125 / 60. Content hash re-pinned
  (84bac9e8… → 621cd52c…).
- `tests/physics/test_thermal.py`, `tests/metrics/test_physics.py`,
  `tests/core/test_coverage_paydown_v20.py`,
  `tests/core/test_specification_rust_differential.py`,
  `tests/physics/test_thermal_potential.py` — pins updated to the
  corrected values (ambient 60, datasheet R defaults, margin 80 - Ts).

All updated pins are *stricter or equal* to the physics they replace — none
weaken a check.

---

## 4. Deliberately NOT changed (with reasons)

- **`simulation/models/IKW40N120H3_thermal.sub` (RthetaJC = 0.6 K/W)** — kept.
  The decision doc §3.2 notes the SPICE model's 0.6 stand-in is ~2× the
  datasheet 0.31, i.e. **conservative** (overestimates Tj) — the safe
  direction. Changing it to the datasheet value would make the simulation
  *less* pessimistic; per the repo rule "never make a check pass by
  weakening it", it stays, flagged in the decision doc.
- **The generic RJC package lookup** (`_RJC_PACKAGE_LOOKUP` /
  `RJC_PACKAGE_LOOKUP` / `infer_rjc`, TO-247 → 0.6) — kept, three-way
  mirrored. It is a *package-class* stand-in for arbitrary TO-247 parts,
  not the IKW40N120H3's per-part Rjc; the per-part datasheet value is now
  applied at the analysis call sites via `thermal_resistance_for`. A
  future per-part table should supersede the package table, not mutate it.
- **The edge-distance penalty heuristic** (`0.2 K/W per mm beyond 5 mm`
  in `measure_thermal_edges`) — kept in the metric (it is a placement
  metric for board-mounted heat sources), but the board analysis does NOT
  apply it to HS1-mounted devices: their sink path is the chassis
  heatsink, not the board edge. Applying it to a mid-board IGBT adds
  ~14 K/W of artifact resistance and manufactures a fake red. **Known
  limitation:** the metric itself still applies the penalty to all devices
  — flagged for a future per-device "sink path" flag, out of scope here.
- **`docs/` re-points** (THERMAL_DESIGN_GUIDE §3.1/§8 margin 150 →
  125/175, SYSTEM_THERMAL_BUDGET §8.3 "Max Tj 150 → 175",
  SAFETY_INTERLOCK_DESIGN §5.1 rationale) — listed in the decision doc §7
  as owner follow-ups; the analysis code is corrected here. The docs carry
  the same 150 °C storage-temp confusion and should be re-pointed in a
  docs-only follow-up.

---

## 5. Verification

- `cargo test -p temper-thermal` — 2752 passed, including the reworked
  `thermal_edges` kernel tests (chain values hand-verified: 54.4 / 46.75 /
  5.0 for the 15 W edge-mounted case) and the new proptest properties
  (`max_ts ≥ ambient`, `max_ts ≤ max_tj`).
- `tests/physics/`, `tests/metrics/`, `tests/core/`, `tests/validation/`
  (temper-placer) — pass except `test_thermal_battery_run.py`, which
  aborts on **ngspice not installed** (environmental; verified identical on
  `origin/main`).
- `scripts/check_oracle_hashes.py` — only the two pre-existing DRIFTED
  deterministic oracles remain (verified identical on `origin/main`,
  unrelated to this change).
- `scripts/gen_wasm_test_registry.py --check` — up to date (no new
  `#[test]` names added to the wasm-reachable modules).
- `tools/wasm/gen_property_campaign.py --check` — stale, but targets
  `temper-drc-rs` (a crate this change does not touch); verified stale on
  `origin/main` too (pre-existing).

---

## 6. Open items this change surfaces

1. The **edge-penalty sink-path flag** for `measure_thermal_edges` (see §4)
   — the placement metric over-penalises mid-board heatsink-mounted
   devices. Needs a per-device "heatsink-mounted" input; out of scope here.
2. The **TO-220 rectifier dissipation** (U1/U2) is not recorded in-repo —
   the 5 W placeholder makes their row approximate. Datasheet recovery for
   the rectifier parts would firm up Rjc too.
3. The **docs re-points** (§4) — the 150 °C storage-temp confusion still
   lives in `THERMAL_DESIGN_GUIDE.md`, `SYSTEM_THERMAL_BUDGET.md`, and
   `SAFETY_INTERLOCK_DESIGN.md`; the decision doc §7 lists them.
