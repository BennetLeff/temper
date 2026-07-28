# OVP-01 Option C implementation: re-reference comp.INN to REF2025

<!-- provenance: commit=220fd89ac45b5e5efa8b3be365af3e1653ed2967 dirty=true -->

**Date:** 2026-07-27
**Scope:** Implementation. Modifies `elec/src/modules.ato`, `elec/src/main.ato`,
`elec/domain_manifest.yaml` (comments only, no chain/boundary changes), and
`simulation/harness/`.
**Subject:** OVP-01 (`OVPComparator`, `elec/src/modules.ato`).
**Selects:** Option C from
`docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md` Part 3.

---

## Falsifiers

Stated before implementing:

1. **"This implementation fails if the E96 sweep cannot find an
   `r_div_bot`/`r_hyst` pair, referenced to REF2025's fixed 2.5V VREF, that
   clears the 195-205V trip / 5-10V hysteresis window under worst-case
   tolerance **and** tempco (not tolerance alone) at a 45-60°C board rise.
   In that case Option C does not actually close OVP-01 and a different
   option (B, A, or spec-widening) is needed instead."**
   **Did not fire.** An exhaustive E96 sweep (608 candidate pairs, script
   below) found 16.9kΩ/487kΩ clearing both windows with margin at ΔT=60°C
   (196.11-203.81V trip, 8.58-8.90V hysteresis against 195-205V/5-10V).

2. **"If deleting `r_ref_top`/`r_ref_bot` shifts other components'
   auto-assigned reference designators enough to break the physical-
   placement safety suite (a documented failure mode in this codebase --
   see `docs/evidence/2026-07-27-pcb-netlist-resync.md`), that is a real,
   disclosed regression requiring a `pcb/` resync, which is out of this
   task's scope (`pcb/` is owned by a separate concurrent agent)."**
   **Did fire.** See "Safety suite result" below. This is reported
   honestly as 53/54, not rounded up to 54.

---

## Re-derivation (not copied from the prior stale-base attempt)

### What changed and why

`comp.INN` was previously referenced by `r_ref_top`/`r_ref_bot`, a 1%
resistor divider off `power.vcc` (3.3V). Both resistors are **deleted**.
`comp.INN` is now driven directly by **REF2025's VREF pin** (2.5V fixed,
±0.05% initial accuracy, 8ppm/°C max tempco) -- REF2025 is already
instantiated in `RTDSensing` (`main.ato`'s `rtd_pan`), on the same
`power_3v3`/`gnd` domain as `OVPComparator`. Its `VBIAS` (1.25V) output
already drives `RTDSensing`'s RTD-window dividers (~96µA total); its `VREF`
(2.5V) output was verified **completely unused** elsewhere in the design
(grepped every `.VREF` reference in `elec/src/*.ato` before this change --
zero hits). REF2025's rated output current is 20mA; the only load on VREF
after this change is the TLV3201's CMOS input bias current (picoamp range
-- REF2025's output is a buffered, actively-driven node, not a resistive
divider, so no loading resistor is needed at all, unlike the divider it
replaces).

### Circuit model

```
Rtop = r_div_top1 + r_div_top2 + r_div_top3   (3 x 430kΩ, unchanged, 1,290,000Ω)
N    = 1 + Rtop/r_div_bot
Vref = 2.5V (REF2025.VREF, fixed -- no longer a VCC-derived ratio)
V_trip     = Vref * (N + Rtop/r_hyst)
hysteresis = VCC * Rtop / r_hyst          (VCC = 3.3V comp.OUT swing; unchanged
                                            formula -- the feedback path from
                                            comp.OUT to comp.INP never involved
                                            Vref)
```

### Deriving r_div_bot and r_hyst

First pass (ignoring the small `Rtop/r_hyst` additive term) targets
`r_div_bot ≈ 1,290,000 / ((200/2.5) - 1) ≈ 16,329Ω`; nearest E96 candidates
cluster around 16.2k/16.5k/16.9k/17.4k. For hysteresis centred at ~7.5V,
`r_hyst ≈ VCC*Rtop/7.5 ≈ 567,600Ω`.

An **exhaustive E96 grid search** (all E96 members from 13.0k-20.0k for
`r_div_bot` × all E96 members from 350k-750k for `r_hyst`, 19 × 32 = 608
pairs) was run, computing the independent-corner worst case (64 corners:
3 × `r_div_top` signs, `r_div_bot` sign, `r_hyst` sign, `Vref` sign) at
±1%/±100ppm·°C on the three 430k resistors, ±0.1%/±25ppm·°C on `r_div_bot`
and `r_hyst` (matching this project's existing 0.1% thin-film RT-series
parts), and ±0.05%/8ppm·°C on Vref, at ΔT=60°C. The pair maximizing the
worst-case margin to either window edge is:

**`r_div_bot = 16.9kΩ`, `r_hyst = 487kΩ`** -- both confirmed E96 members
(mantissas 1.69 and 4.87, both in the standard E96 sequence).

This **matches** the values named in the task brief as "a starting
hypothesis from a stale-base attempt" (`16.9kΩ`/`487kΩ`). That match is a
result of the independent re-derivation at HEAD, not an assumption carried
over -- the search script (below) was run fresh against the current
`Rtop = 1,290,000Ω` (unchanged since the stale attempt; the three 430k
resistors were never touched) and the current REF2025 Vref spec, and
converged on the same pair as the global optimum over the full 608-pair
grid, not merely as one candidate among several considered.

Nominal result: **V_trip = 199.95V, hysteresis = 8.74V** (both centred in
their windows: 195-205V and 5-10V respectively).

Search script (re-runnable, not committed under `elec/` or `scripts/` per
this task's ownership boundary -- ad hoc, in the session scratchpad):
grid search over `itertools.product` sign corners, closed-form trip/hyst
per corner, margin = `min(trip_min-195, 205-trip_max, hyst_min-5, 10-hyst_max)`.

### Worst-case bounds

| Case | Trip range | Hysteresis range | Vs. window |
|---|---|---|---|
| Nominal | 199.95 V | 8.74 V | centred |
| **Tolerance only** (±1% top-3, ±0.1% bot/hyst, ±0.05% Vref, no tempco) | **197.68 - 202.23 V** | 8.65 - 8.84 V | passes, ~2.3-2.8V margin |
| **Tolerance + tempco, ΔT=45°C** (uncorrelated worst case) | **196.51 - 203.42 V** | 8.60 - 8.89 V | passes, ~1.6-1.9V margin |
| **Tolerance + tempco, ΔT=60°C** (uncorrelated worst case) | **196.11 - 203.81 V** | 8.58 - 8.90 V | **passes, ~1.1-1.2V margin** |

Board-ambient ΔT assumption (45-60°C) carried over unchanged from
`docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md` -- no new
measurement was taken for this board region; flagged there as an assumption,
not a verified fact, and repeated here as such (see UNVERIFIED below).

This is the **independent worst-case** figure (all sources at their
extreme simultaneously, no reliance on statistical cancellation), the same
standard the prior evidence doc used to correctly fail the divider-
referenced design (193.9-206.2V tolerance-only, before tempco). Under that
same standard, the REF2025-referenced design **clears the window even with
tempco included at the more conservative 60°C assumption** -- the prior
design did not clear it even without tempco.

### Assertion re-expression

The pre-existing assertion (verifies the trip point stays below the window
at a representative 180V below-trip bus voltage) referenced
`r_ref_bot.value`/`r_ref_top.value`, which no longer exist. Re-expressed
against REF2025's fixed output as a literal (there is no component field
to read 2.5V from -- the same reason `VCC` was already a literal `3.3V`
in this assertion before this change):

```
assert 180V * (r_div_bot.value / (r_div_top1.value + r_div_top2.value + r_div_top3.value + r_div_bot.value)) < 2.5V
```

Confirmed passing in the `make netlist` assertions report: `2.3 to 2.35 V
< 2.5V` (range reflects `r_div_bot`'s ±0.1% and the three `r_div_top`
resistors' ±1% tolerance bands).

### Protective-impedance chain: unaffected

`elec/domain_manifest.yaml`'s `ovp01_comparator_divider` chain declares
only `r_div_top1/2/3` (`min_length: 3`) -- `r_div_bot` was never a chain
member. Changing its value from 10k to 16.9k does not move the chain's
declared boundary node (`safety.ovp.comp-inp`, still the same net). No
`min_length`/chain-membership edit was needed. Three narrative comments in
the manifest that quoted `r_div_bot`'s old value/MPN or a stale reference
voltage from an even earlier fail-open design (2.973V, pre-dating even the
2026-07-27 half-bus retune) were updated for accuracy (documentation-sync,
not gate-required) -- `check_domain_partition.py` re-confirmed passing
after the edit (comments only, no structural change).

---

## Parts: E-series and distributor confirmation

| Ref | Old | New | Value | Tolerance | Tempco | E-series | MPN | Distributor confirmation |
|---|---|---|---|---|---|---|---|---|
| R54 | `r_div_bot` | `r_div_bot` | 16.9kΩ | ±0.1% | ±25ppm/°C | E96 (mantissa 1.69) | `RT0603BRD0716K9L` | DigiKey product page fetched directly this session: 16.9kΩ, ±0.1%, ±25ppm/°C, 0603, active/in-stock (24,437 units) |
| R55 | `r_hyst` (was 619kΩ) | `r_hyst` | 487kΩ | ±0.1% | ±25ppm/°C | E96 (mantissa 4.87) | `RT0603BRD07487KL` | DigiKey product page fetched directly this session: 487kΩ, ±0.1%, ±25ppm/°C, 0603, active/orderable (9,130 units) |
| -- | `r_ref_top` (11.8kΩ) | **deleted** | -- | -- | -- | -- | -- | n/a -- removed from BOM |
| -- | `r_ref_bot` (10kΩ) | **deleted** | -- | -- | -- | -- | -- | n/a -- removed from BOM |
| U10 | `RTDSensing.reference` | unchanged, new net on existing pin | 2.5V (VREF pin) | ±0.05% | 8ppm/°C max | n/a (IC) | `REF2025AIDDCR` (already in BOM) | DigiKey product page + TI product page (`ti.com/product/REF2025`), both fetched directly this session: initial accuracy 0.05% max, tempco 8ppm/°C max. Both sources describe device-level accuracy without a table separating VBIAS(=VREF/2) vs VREF -- see UNVERIFIED. |

`r_div_top1/2/3` (430kΩ ±1%, `RC1206FR-07430KL`) are **unchanged** -- the
task's hard requirement that the protective-impedance chain not move.

`mpn_fabrication_gate.py` re-run after the change: **0 new violations**,
118 parts inspected (7 `.ato` files), 118 values checked for E-series
membership, 99 MPNs decoded against a known manufacturer-prefix family, 19
unchecked (unrecognised prefix, reported not silently passed -- the two new
`RT0603BRD...` parts fall here, since the gate's MPN-decoder only recognises
Yageo RC/RSF, not RT, but their **values** were independently checked
against E96 and passed), 10 pre-existing allowlist entries (none new, none
touching this change).

---

## Simulation

`simulation/harness/run_ovp01_sim.py` and
`simulation/harness/nets/ovp01_trip_point.cir` updated: the
`r_ref_top`/`r_ref_bot` divider is replaced with an ideal `V_VREF vinn 0 DC
2.5` source (modelling REF2025's buffered output for a nominal-only SPICE
run -- worst-case tolerance+tempco is the separate hand/script analysis
above, not a SPICE sweep); `r_div_bot` changed to 16900, `r_hyst` to 487000.

5-run determinism check: **deterministic across 5 runs (byte-identical
ngspice stdout)**.

| Quantity | Simulated | Hand-derived | Agreement |
|---|---|---|---|
| Trip (v_bus.line) | 200.029 V | 199.95 V | 0.079 V |
| Release (v_bus.line) | 191.24 V | 191.21 V | 0.030 V |
| Hysteresis | 8.789 V | 8.74 V | 0.05 V |

Both trip and release are **within** the 195-205V / 5-10V half-bus-
equivalent windows. Evidence JSON:
`docs/evidence/2026-07-27-ovp01-ref2025-trip-point-sim.json`
(`schema_version: 1`, `calibrated: false`, matches the existing schema of
`docs/evidence/2026-07-27-ovp01-trip-point-sim.json` field-for-field).

---

## Gate results (counts, not bare exit codes)

All measured against the final committed state (`make netlist` re-run
after every source edit):

- **`make netlist`**: builds clean. **76 assertions, 76 PASSED, 0 FAILED**
  (matches the pre-existing count -- no assertion added or removed, one
  re-expressed).
- **`check_domain_partition.py`**: exit 0. "Checked 48 declared nets across
  2 domains (HV, SELV), 10 declared isolators, 2 declared
  protective-impedance chain(s) (6 chain member(s) total), over 164
  compiled nets / 168 components. PASSED -- 0 domain crossings, 0
  isolator-barrier breaches, 0 protective-impedance chain defects."
- **`capacity_budget_gate.py`**: exit 0. "Design capacity budget gate
  PASSED -- 0 defects" (fault-tree fan-in budget; `r_hyst`'s new MPN shows
  correctly at R55 in the gate's own occupancy report).
- **`mpn_fabrication_gate.py`**: exit 0. 118 parts inspected, 0 new
  violations (see Parts table above for the full breakdown).
- **`check_derived_doc_drift.py`**: exit 0. "3 document(s), 44 table(s)
  parsed, 52 gate row(s) matched, 132 field(s) checked" -- unaffected by
  this change (this change did not touch `FUNCTIONAL_TEST_CRITERIA.md`,
  `STRATEGY.md`, or `PROTECTION_CHAIN_REVIEW.md`, all outside this task's
  ownership).
- **`check_vacuous_gates.py`**: exit 0. "Scanned 533 file(s)... 0
  violations."

All five stayed exit 0, with real (non-trivial) counts confirming each
gate actually exercised the changed design, not a stale or empty run.

### Safety suite result: 53 passed, 1 failed (NOT 54) -- disclosed, not hidden

`uv run pytest packages/temper-placer/tests/requirements/safety/` (the
`test_clearance.py`/`test_isolation.py` suite the task names) gives **53
passed, 1 failed** with this change in place, vs. **54 passed, 0 failed**
confirmed on baseline HEAD (verified directly: `git stash`, rebuild
netlist, re-run suite, `git stash pop` -- both runs captured to disk).

**Root cause, confirmed not assumed:** deleting `r_ref_top`/`r_ref_bot`
removes two `Resistor` declarations from the middle of `OVPComparator`'s
source order. Atopile assigns reference designators sequentially by
declaration order across the whole compiled design, so every component
declared after them shifts down by two designators (verified directly:
`safety.ovp.r_adc_top1` is `R58` on baseline HEAD and `R56` after this
change; `r_div_bot` and `r_hyst` keep their designators, `R54`/`R55`,
because they are declared *before* the deletion point). The one failing
test, `test_temper_board_clearance_compliance`, cross-references physical
component positions from the **committed, unregenerated**
`pcb/temper.kicad_pcb` (keyed by reference designator) against the
**current** compiled netlist's domain classification. The fixture's own
docstring states its stability assumption explicitly:
`tests/requirements/safety/_real_board_fixture.py`: *"Positions are keyed
by reference designator, which is stable across a net rename -- unlike net
names, a ref does not change when the schematic is edited to rename or
re-scope a net."* That assumption holds for net renames; it does not hold
across a **component-count change**, which this task's own requirement 2
("Delete r_ref_top and r_ref_bot") mandates. After the shift, the
designator that used to belong to `r_ref_bot` (not HV-classified) now
belongs to `r_adc_top1` (HV-classified, part of the declared
`ovp01_adc_sense_divider` chain) -- so three physically-unmoved `rtd_pan`
components (`r_low_top`, `r_ref`, `r_high_top`) that sat near that
board location are newly reported as "unclassified component close to a
now-differently-identified HV component."

**This is not a new physical or electrical hazard.** No component moved on
the board; no new HV/SELV proximity was introduced. It is a **netlist/
placement identity staleness** artifact, of exactly the kind this
codebase has hit and fixed once before (see
`docs/evidence/2026-07-27-pcb-netlist-resync.md`, "78 of 149 shared refs...
drifted") -- and its documented remediation is a `pcb/temper.kicad_pcb`
resync against the current netlist by reference designator/Sheetpath. That
resync is explicitly **out of this task's scope**: this task's own
constraints assign `pcb/` to a separate, concurrently-running agent and
forbid this agent from touching it ("Do NOT modify `pcb/`... three other
agents are running -- on `pcb/`, `scripts/`, and docs-only analysis").
Any schematic-level change that changes OVPComparator's component count --
which Option C's explicit deletion requirement makes unavoidable -- will
trigger this same consequence until the board is resynced.

Reported as: **53/54, not 54/54**, with full root-cause attribution,
rather than claimed as unaffected. Fixing it requires a `pcb/` change this
task is not permitted to make.

---

## UNVERIFIED list

- **REF2025's VREF-specific (vs. VBIAS-specific) accuracy/tempco spec.**
  Both DigiKey's and TI's product pages, fetched directly this session,
  report device-level "0.05% initial accuracy, 8ppm/°C max tempco" without
  a spec-table row visibly distinguishing the VBIAS (1.25V, = VREF/2) output
  from the VREF (2.5V) output. Since VBIAS is derived from VREF by a fixed
  internal ratio (per the component's own docstring, "2.5V / 1.25V
  precision reference"), the same relative accuracy is expected to apply to
  both, but a full datasheet table split by output pin was not read this
  session (TI's PDF datasheet was not fetched as readable text; only the
  DigiKey and `ti.com/product/REF2025` summary pages were).
- **Board-ambient ΔT (45-60°C) assumption.** Carried over unchanged from
  `docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md` -- not
  a new measurement, still an inference from analogous board-zone figures
  elsewhere in this repo, not a direct measurement of this specific board
  region.
- **REF2025-to-comp.INN trace routing/noise feasibility.** This crosses
  between two different top-level module instances (`rtd_pan` and
  `safety.ovp`) physically on the board. Physical proximity, trace length,
  and noise pickup on this precision analog reference trace were not
  checked in this pass -- same open item the sensitivity-budget evidence
  doc already flagged for Option C, still open after implementation.
- **The 390-410V/10-20V full-bus OVP-01 window's own provenance.** As
  established in the sensitivity-budget evidence doc: introduced in a bulk
  commit (`3f27dc58`) with no supporting derivation, though bounded by two
  cited engineering constraints (`v_bus_max=340V`, `v_cap_max=500V`). Not
  re-investigated in this pass; irrelevant to this task's outcome since
  Option C clears the window as given, so no need to weaken it arose.
- **`pcb/temper.kicad_pcb` resync following this change.** Confirmed
  necessary (see "Safety suite result" above); confirmed out of scope for
  this task; not performed here.
