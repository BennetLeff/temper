---
date: 2026-07-25
topic: spice-harness-zvs-sweep
---

# SPICE Harness: ZVS Margin Sweep and Protection-Threshold Verification

## Summary

`simulation/` contains 13 vendor SPICE model files and **no harness to run
them**. Those models are a nearly complete kit for the power stage and
protection chain. This proposes building the harness and running two
simulations: a ZVS-margin sweep across the pan-load space, and transient
verification of the protection trip points. It is the only work that addresses
"the schematic is not validated," and it is the highest-return simulation
available per `docs/METHODOLOGY.md` §11.

---

## Problem Frame

`docs/STRATEGY.md` records the schematic as unvalidated on every axis: no clean
ERC, no power-stage simulation, no component values verified against computed
stress, no review by an experienced power-electronics engineer.

ERC was run for the first time on 2026-07-25: **438 warnings, zero errors**
(149 `lib_symbol_issues`, 146 `footprint_link_issues`, 143 `endpoint_off_grid`).
That is reassuring about gross wiring and says **nothing** about circuit
correctness. ERC cannot tell you whether the tank holds ZVS or whether OCP trips
inside 45–55 A. The schematic-trust problem is untouched.

Meanwhile the models are already present:

| Model | Covers |
|---|---|
| `IKW40N120H3.lib`, `IKW40N120H3_thermal.sub` | IGBT, electrical + thermal |
| `pan_load.sub`, `current_transformer.sub` | resonant tank and sensing |
| `UCC14140_behavioral.sub` | isolated gate drive |
| `TLV3201`, `TPS3700`, `REF2025` | protection comparators and reference |
| `LMR51430_avg.lib`, `XC6220_3V3`, `LDO_3V3` | rails |
| `SN74LVC1G08`, `SN74LVC1G38` | logic |

Thirteen files, zero harness. The most expensive part of a simulation effort is
already done.

**The asymmetry that justifies this:** compute is nearly free; physical ground
truth is expensive and rate-limiting. A ZVS sweep covers thousands of operating
points overnight. A bench covers the pans in one kitchen. Losing ZVS destroys
the IGBT, and it is the core failure mode of an induction cooker.

---

## Requirements

- **R1.** An ngspice harness that loads a netlist plus the models in
  `simulation/models/`, runs a parameterized transient, and returns structured
  results. Scriptable and non-interactive — it must run in CI, not only by hand.

- **R2.** **ZVS margin sweep.** Sweep pan inductance, coupling, resistance,
  switching frequency, and power level. Assert ZVS margin at every operating
  point. Output identifies the operating points with the worst margin, not only
  a pass/fail.

- **R3.** **Protection-threshold transients** for OCP-01 (45–55 A, **<1 µs**),
  OCP-02 (55–65 A, <5 µs), OVP-01 (390–410 V), UVL-01/02. The sub-microsecond
  figure is a propagation-delay budget that can be verified before any bench
  trip exists.

- **R4.** **Every model carries a machine-readable `calibrated: true|false`
  tag that propagates into any verdict depending on it.** No bench data exists
  yet, so every result from this work is provisional by construction. A verdict
  built on uncalibrated models must say so in its output —
  `METHODOLOGY.md` §11.

- **R5.** **The bench bring-up measurement list is derived from what the models
  need**, not written independently. Coil L and Q under real pans, IGBT thermal
  impedance, comparator propagation delay. First power-on becomes a designed
  calibration experiment rather than a smoke test.

- **R6.** Results are reproducible from a committed command, and stored as
  evidence under `docs/evidence/` with the invocation recorded — matching the
  discipline applied to router measurements.

---

## Success Criteria

- ZVS margin is known across the declared pan-load envelope, with the worst
  operating points identified by name.
- Each protection gate has a simulated trip value and latency, tagged
  uncalibrated.
- Re-running any published figure reproduces it.

---

## Scope Boundaries

**In scope:** the harness, the ZVS sweep, protection transients, calibration
tagging, the derived bench measurement list.

**Out of scope:**
- **EMI/CISPR prediction.** Simulation will not predict Class B pass/fail.
  Loop-area and dv/dt ranking is a separate, later, explicitly-bounded effort.
- Monte Carlo tolerance analysis — valuable (`METHODOLOGY.md` §11 rank 3) but
  it depends on this harness existing first.
- Thermal FEM. `IKW40N120H3_thermal.sub` supports lumped thermal here; field
  simulation is separate.
- Any schematic *change*. This work measures; it does not redesign.
- Firmware HIL-in-simulation — depends on this harness, deferred.

---

## Key Decisions

- **ZVS sweep before protection transients.** Losing ZVS destroys the IGBT and
  invalidates everything downstream. Protection thresholds matter only on a
  power stage that survives normal operation.
- **Calibration tagging from day one, not retrofitted.** The failure mode this
  guards against is a board that passes every model we wrote and fails through
  a mechanism we never modelled. Retrofitting the tag after results circulate
  is how uncalibrated numbers become trusted.
- **Bench plan derived backward from the models.** This is what converts one
  physical board into a permanently cheaper simulation layer, which is the
  long-term goal in `STRATEGY.md`.

---

## Dependencies / Assumptions

- Assumes the 13 vendor models are usable as-is under ngspice. Some are
  behavioral (`UCC14140_behavioral.sub`) and their fidelity limits should be
  stated rather than discovered.
- Assumes a netlist can be extracted from `elec/` or `pcb/` in a form ngspice
  accepts. This is unverified and is the most likely source of unexpected work.
- Independent of the pipeline loop — needs no routing and no valid placement
  (`METHODOLOGY.md` §9).

---

## Outstanding Questions

- What is the declared pan-load envelope? The sweep bounds are a product
  decision (which cookware is supported) that nothing currently records.
- Does a usable SPICE netlist already exist, or must it be generated from
  atopile? This is the single largest unknown in scope.
- Is the IGBT model's switching behavior trustworthy enough for ZVS margin, or
  does it need vendor validation? A vendor model that is accurate for
  conduction loss may be poor at turn-off tail.
- Who reviews the results? Simulation without power-electronics review
  substitutes one unvalidated artifact for another.

### Deferred to Planning

- ngspice vs. alternatives.
- Whether sweeps run in CI or as an offline batch, given hour-scale runtimes.
- Surrogate-model fitting to make sweep results usable in an inner loop.
