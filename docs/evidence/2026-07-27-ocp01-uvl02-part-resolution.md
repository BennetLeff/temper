# OCP-01 / UVL-02 protection-divider part resolution — 2026-07-27

<!-- provenance: commit=ed89a3a2181d35397b9047ba3344c5ce573e1ec4 dirty=UNKNOWN -->

**Scope:** two `mpn_fabrication_gate.py` findings in protection circuits:
`OCPComparator.r_ref_top` (`elec/src/modules.ato`) and
`LogicUVLOComparator.r_div_bot` (`elec/src/modules.ato`). Both set a safety
threshold, so both required re-deriving the trip point, not just swapping a
part number. No `pcb/` files were touched.

**Base:** confirmed on `docs/methodology-loop-discipline`
(`scripts/assert-base.sh` exit 0, HEAD `9f79346758ab7ddf1d4b6bb6bcd604c009603398`)
before any edit. `scripts/mpn_fabrication_gate.py` was run first and
confirmed still exit 3 with 5 findings (including both of these) before any
implementation — the audit/gate commits already on this branch
(`26658389`, `186a57d8`) found and report these defects but do not fix them.

---

## Defect 1 — OCP-01, `OCPComparator.r_ref_top`

### Falsifier (stated before implementing)

> If no real E96 value near 3.2 kΩ keeps the worst-case OCP-01 trip
> (initial ±1% tolerance **and** ±100 ppm/°C tempco at ΔT=60°C) inside the
> 45–55 A window, this fix fails and a topology change (not a value swap)
> is required.

**Did not fire.** The real E96 neighbour 3.24 kΩ keeps worst-case trip at
48.77–51.16 A (tolerance+tempco) — see Simulation below.

### Which field was wrong, and how established

`r_ref_top.value = 3200ohm`, `r_ref_top.mpn = "RC0603FR-073K2L"`.

- **3.2 kΩ is not an E24 or E96 member.** Computed directly: the E96
  sequence around 3.2k is …3.09k, 3.16k, 3.24k, 3.32k… — no 3.2k. `scripts/mpn_fabrication_gate.py`
  independently reports the same two neighbours.
- **`RC0603FR-073K2L` returns zero results on DigiKey**, fetched directly
  this session (`https://www.digikey.com/en/products/result?keywords=RC0603FR-073K2L`
  → "Sorry, 'RC0603FR-073K2L' did not return any results."). Mouser was not
  independently queried this session either, but the DigiKey zero-hit result
  plus the E96 non-membership together confirm fabrication (same signature
  as the already-confirmed `ERA-3AEB6132V`/61.3kΩ case): the value encodes
  a non-standard number and the MPN string encodes that same invented
  number ("3K2"), so nothing here is a typo of a real, catalog part.
- **Verdict: CONFIRMED fabricated**, not merely unverified — a live
  distributor page was actually reached and returned zero hits.

### Re-derivation, with arithmetic

Circuit (`OCPComparator` + `CurrentSensing`, unchanged topology):
CT ratio N=100, burden `r_burden=4.99Ω`, comparator reference divider
`Vref = VCC · r_ref_bot / (r_ref_top + r_ref_bot)` with `VCC=3.3V` (from
`power_3v3`), `r_ref_bot=10kΩ` (unchanged, real part `RC0603FR-0710KL`,
confirmed decoding to 10kΩ). Trip current `I_trip = Vref · N / r_burden`.

Candidates (both real E96 neighbours of the fabricated 3.2k):

| r_ref_top | Vref | I_trip (nominal) | \|I_trip − 50.0\| |
|---|---|---|---|
| 3.16 kΩ | 2.5076 V | 50.25 A | 0.25 A |
| **3.24 kΩ** | **2.4925 V** | **49.95 A** | **0.05 A** |

**Chose 3.24 kΩ** — closer to the 45–55 A window's 50.0 A midpoint.
MPN: `RC0603FR-073K24L`.

**Distributor confirmation (fetched this session, DigiKey):**
`RC0603FR-073K24L` — 3.24 kΩ, ±1%, 0603, ±100 ppm/°C, Yageo, real product
page. `RC0603FR-07100KL` (used below for Defect 2) and `RC0603FR-0710KL`
(unchanged `r_ref_bot`) were also independently fetched and confirmed.

### Worst-case: initial tolerance, then + tempco

Method: exhaustive corner sweep over `r_ref_top`, `r_ref_bot`, `r_burden`,
each independently at its worst-case fractional error (script:
`simulation/harness/run_ocp01_sim.py::worst_case_corners`, also captured in
`docs/evidence/2026-07-27-ocp01-trip-point-sim.json`). Tempco figure
(±100 ppm/°C, Yageo RC-series, DigiKey-verified) and the ΔT=60°C "extreme
ambient" convention both carried over from
`docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md`, which
argues tolerance and tempco should stack (not RSS-combine) for a
protection circuit's safety case, since there is no supplier
correlation/matched-lot guarantee for these parts.

| Case | I_trip range | vs. 45–55 A |
|---|---|---|
| Nominal | 49.95–49.97 A (hand-derived / simulated) | centred |
| Tolerance only (±1%, 3 resistors) | 49.21–50.70 A | passes, wide margin |
| **Tolerance + tempco (ΔT=60°C)** | **48.77–51.16 A** | **passes, wide margin** |
| Bonus: + VCC ±5% (`BuckConverter3V3`'s own asserted regulation tolerance — not part of the original design's worst-case scope, checked here for completeness) | 46.34–53.71 A | still passes, ~1.3 A margin each side |

The bonus VCC-tolerance check is reported for completeness; it is not part
of what the original `CurrentSensing` design comment scoped ("burden and
both OCPComparator reference resistors" only), and is not required to
close this defect, but is worth flagging since it is a real, unquantified
error term on the same rail — see UNVERIFIED list.

### Simulation

`uv run python simulation/harness/run_ocp01_sim.py --runs 5` (ngspice,
foreground, exit 0): 5/5 byte-identical stdout (deterministic). Netlist
(`simulation/harness/nets/ocp01_trip_point.cir`) updated to the corrected
3240Ω to match the committed value (it previously hardcoded 3200Ω
independently of the Python harness's constant).

- **Measured trip current: 49.971 A** (within 45–55 A). Matches the
  hand-derivation (49.95 A) to within simulation quantization.
- **Worst-case (tolerance + tempco): 48.774–51.155 A**, within window.
- `calibrated: false` preserved throughout (no bench measurement of this
  board exists). Evidence: `docs/evidence/2026-07-27-ocp01-trip-point-sim.json`.

---

## Defect 2 — UVL-02, `LogicUVLOComparator.r_div_bot`

### Falsifier (stated before implementing)

> Re-derive `VCC_trip`/`VCC_recover` from the circuit with `r_div_bot` at
> each of its two candidate values (100 kΩ as declared, 10 kΩ as the MPN
> encodes). If the value that the MPN encodes (10 kΩ) produces a
> plausible in-window result while 100 kΩ does not, the *value* is the
> error, not the MPN. If neither produces a plausible result, something
> else is wrong.

**Did not fire against the "value is wrong" hypothesis; the MPN is wrong.**
100 kΩ reproduces the module's own documented worst-case figures exactly;
10 kΩ produces a physically unreachable result (below).

### Which field was wrong, and how established

`r_div_bot.value = 100kohm`, `r_div_bot.mpn = "RC0603FR-0710KL"`.
Yageo's RC-series MPN convention decodes `10KL` → 10 kΩ — a 10x mismatch
against the declared value.

Re-derived independently from `LogicUVLOComparator`'s own Millman circuit
(`r_div_top=698kΩ`, `r_hyst=3.74MΩ` fixed, `VIT_A≈394.5mV` nominal,
383–400mV datasheet range) with each candidate for `r_div_bot`:

```
G_t = 1/r_div_top,  G_b = 1/r_div_bot,  G_h = 1/r_hyst
VCC_trip    = VIT_A * (G_t+G_b+G_h) / (G_t+G_h)
VCC_recover = VIT_A * (G_t+G_b+G_h) / G_t
```

| r_div_bot | VCC_trip (nominal) | VCC_recover (nominal) |
|---|---|---|
| **100 kΩ (declared)** | **2.715 V** | **3.222 V** |
| 10 kΩ (MPN's encoding) | 23.60 V | 28.00 V |

100 kΩ reproduces `LogicUVLOComparator`'s own docstring (2.715V/3.222V
nominal) and `docs/hardware/UVL02_DESIGN.md`'s worst-case corner sweep
(≤2.800V trip / ≥3.106V recovery) exactly. 10 kΩ gives trip/recovery
voltages far above the 3.3V rail the comparator is powered from —
physically unreachable, i.e. an under-voltage lockout that would never
trip. **Verdict: the value (100 kΩ) is correct; the MPN was wrong.**
Ordered as originally written, the board would have received a real,
correctly-manufactured 10 kΩ resistor and assembled a UVLO that never
fires — no distributor/availability check would have caught it, since the
part itself is real.

**Fix:** `r_div_bot.mpn = "RC0603FR-07100KL"` (value unchanged at 100 kΩ).
This is the same MPN pattern already used elsewhere in this file for real
100 kΩ 1% 0603 parts (e.g. `RTDSensing.r_window_ok_pulldown`,
`BuckConverter3V3.r_fb_top`), which the gate does not flag.

**Distributor confirmation (fetched this session, DigiKey):**
`RC0603FR-07100KL` — 100 kΩ, ±1%, 0603, ±100 ppm/°C, Yageo, in stock
(>2.9M units), real product page.

### Worst-case: initial tolerance, then + tempco

Method: 16-corner sweep (`r_div_top`, `r_div_bot`, `r_hyst` each
independently at worst-case tolerance, `VIT_A` at datasheet min/max),
extended this session with a tempco variant
(`simulation/harness/run_uvl02_logic_sim.py::worst_case_corners_with_tempco`),
same ±100 ppm/°C / ΔT=60°C convention as Defect 1.

| Case | Trip (ceiling 2.9V) | Recovery (floor 3.0V) |
|---|---|---|
| Nominal | 2.715–2.716 V | 3.222 V |
| Tolerance only (±1% + VIT_A range) | ≤ 2.8004 V (100mV margin) | ≥ 3.1056 V (106mV margin) |
| **Tolerance + tempco (ΔT=60°C)** | **≤ 2.8294 V (70.6mV margin)** | **≥ 3.0731 V (73.1mV margin)** |

Both clear their windows even under the combined worst case, though with
reduced margin versus tolerance alone — consistent with
`docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md`'s prior,
independently-run UVL-02 tempco analysis (which used the same 100kΩ value
and got the same figures to 4 decimal places, cross-validating both this
session's model and that document's).

### Simulation

`uv run python simulation/harness/run_uvl02_logic_sim.py --runs 5`
(ngspice, foreground, exit 0): 5/5 byte-identical stdout (deterministic).
The netlist (`simulation/harness/nets/uvl02_logic_uvlo_trip_point.cir`)
already hardcoded `r_div_bot=100000` (the correct value), so the MPN-only
fix required no netlist change.

- **Measured trip: 2.7160 V** (< 2.9V ceiling). **Measured recovery:
  3.2217 V** (> 3.0V floor). Hysteresis 0.5057V.
- **Worst-case (tolerance only): trip ≤ 2.8004V, recovery ≥ 3.1056V** —
  within spec.
- **Worst-case (tolerance + tempco, ΔT=60°C): trip ≤ 2.8294V, recovery ≥
  3.0731V** — within spec.
- `calibrated: false` preserved throughout. Evidence:
  `docs/evidence/2026-07-27-uvl02-logic-uvlo-sim.json`.

---

## Verification summary

| Check | Result |
|---|---|
| `scripts/assert-base.sh docs/methodology-loop-discipline` | exit 0 |
| `scripts/mpn_fabrication_gate.py` findings | **5 → 3** (both `r_ref_top` and `r_div_bot` no longer listed; the 3 remaining — `r_low_top`, `r_high_top`, `r_avdd_top` — are OVP-01/RTDSensing findings, out of this task's scope) |
| `make netlist` | exit 0, **76/76 assertions PASSED, 0 FAILED** |
| `scripts/check_domain_partition.py` | exit 0 (0 domain crossings, 0 isolator breaches, 0 protective-impedance defects) |
| `scripts/capacity_budget_gate.py` | exit 0 (0 defects) |
| OCP-01 sim (`run_ocp01_sim.py --runs 5`) | exit 0, deterministic, trip 49.971A, worst-case(tol+tempco) 48.774–51.155A, within 45–55A |
| UVL-02 sim (`run_uvl02_logic_sim.py --runs 5`) | exit 0, deterministic, trip 2.716V / recovery 3.222V, worst-case(tol+tempco) trip≤2.829V / recovery≥3.073V, within <2.9V/>3.0V |

## UNVERIFIED list

- **Mouser was not independently queried for `RC0603FR-073K2L`** this
  session (only DigiKey). The zero-DigiKey-hit result plus E96
  non-membership are treated as sufficient to confirm fabrication (same
  signature as the already-confirmed `ERA-3AEB6132V` case), but a
  from-scratch Mouser cross-check was not performed.
- **OCP-01's worst-case bonus check including the 3.3V rail's own ±5%
  regulation tolerance** (46.34–53.71A) is new analysis added this
  session, beyond the original design comment's scope (which only ever
  considered the burden + reference resistors). It passes with real but
  narrower margin (~1.3A/side) than the resistor-only worst case
  (~1.2–1.3A/side at tempco). This is not required to close Defect 1 but
  is worth carrying forward as a known, now-quantified error term on this
  same VCC-referenced comparator.
- **Board-ambient ΔT=60°C** is the same assumption used in
  `docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md`
  (inferred from analogous board-zone figures elsewhere in this repo, not
  a direct measurement of the OCP-01/UVL-02 comparator locations
  specifically). Not re-verified independently this session; carried
  forward as-is.
- **CT_WITH_BURDEN's RW=50Ω winding-resistance default** (OCP-01 model)
  remains unverified against the real CST3015-100ED datasheet — pre-existing
  limitation, unrelated to this session's fix, unchanged from prior
  evidence docs.
- **Propagation delay** for both gates remains unmeasured (both vendor
  ngspice models declare no timing model) — pre-existing limitation,
  unchanged.
- Both fixes are **MPN/value corrections only** — no PCB, BOM-file, or
  fault-tree wiring changes were made or required. UVL-02's fault output
  remains not wired into the interlock (pre-existing, out of this task's
  scope, tracked separately per `docs/hardware/UVL02_DESIGN.md` SS7).

## Files changed

- `elec/src/modules.ato` — `OCPComparator.r_ref_top` (3200Ω→3240Ω,
  `RC0603FR-073K2L`→`RC0603FR-073K24L`), `LogicUVLOComparator.r_div_bot`
  (MPN only: `RC0603FR-0710KL`→`RC0603FR-07100KL`), plus docstring/comment
  updates recording the re-derivation.
- `simulation/harness/run_ocp01_sim.py` — updated `R_REF_TOP_OHM` constant
  to 3240 to track the corrected committed value; added
  `worst_case_corners()` (tolerance/tempco/VCC-tolerance corner sweep) and
  wired it into the evidence JSON and verdict.
- `simulation/harness/nets/ocp01_trip_point.cir` — updated hardcoded
  `R_REF_TOP` from 3200Ω to 3240Ω (this netlist does not read the Python
  harness's constant; it needed its own edit) and its header comment.
- `simulation/harness/run_uvl02_logic_sim.py` — added
  `worst_case_corners_with_tempco()` and wired it into the evidence JSON
  and verdict (no netlist change needed — value was already correct).
- `docs/evidence/2026-07-27-ocp01-trip-point-sim.json`,
  `docs/evidence/2026-07-27-uvl02-logic-uvlo-sim.json` — regenerated.
- `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md` — this file.
