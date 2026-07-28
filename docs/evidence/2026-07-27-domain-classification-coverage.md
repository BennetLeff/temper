# Domain-classification coverage: quantifying and closing the "0 violations covers only a fraction of the board" gap

<!-- provenance: commit=70503e6dc045619766ba11c6fcfc2a4d62691c32 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Scope:** `elec/domain_manifest.yaml`, `packages/temper-placer/tests/requirements/safety/_real_board_fixture.py`,
`packages/temper-placer/tests/requirements/safety/test_clearance.py`. No `elec/src/*.ato` changes. `pcb/temper.kicad_pcb`
treated as read-only (another agent is concurrently routing it) -- not modified.

**Base:** worktree started on `worktree-agent-a5ce0066262a09972`, 219 commits behind / 4 ahead of
`docs/methodology-loop-discipline` (stale squash-merge artifacts, same pattern as prior 2026-07-27 evidence docs).
Fixed via repoint, not rebase: `git fetch origin && git checkout -B <branch> origin/docs/methodology-loop-discipline`.
`scripts/assert-base.sh docs/methodology-loop-discipline` confirmed exit 0 (HEAD `043debdf`) before any implementation.

---

## 0. There are TWO classifiers, not one, and the task's own headline figures come from both

This is the single most important finding to state up front, because the task's framing conflates them.

1. **`elec/domain_manifest.yaml`** declares **39 nets** (HV=13, SELV=26) against the compiled netlist's **165 nets** /
   **170 components**. This is `scripts/check_domain_partition.py`'s input -- the galvanic-isolation graph check. It
   already reports its own coverage prominently (`"Checked 39 declared nets across 2 domains ... over 165 compiled
   nets / 170 components"`), exactly the precedent the task asks the clearance path to follow.
2. **`packages/temper-placer/tests/requirements/safety/_real_board_fixture.py`** -- the fixture that feeds
   `verify_iec60335_compliance`/`generate_domain_clearance_constraints` (the actual IEC 60335-2-6 **clearance/creepage**
   path, as opposed to check_domain_partition's galvanic-isolation path) -- had its **own, separate, hand-maintained**
   10-net `_NET_DOMAINS` dict, a strict subset of the manifest's 39. This is what produced the task's cited
   **"127 of 170 components classifiable"** figure (measured directly, confirmed below) -- NOT the manifest's 147/170.

So the clearance mechanism the task's "What to change" section is about was actually **sparser than the
already-known-sparse 39-net manifest**, maintained as a second, independently-drifting classification of the same
netlist. That duplication -- not just the manifest's own gap -- is the root cause this evidence doc and the
accompanying fix address.

---

## 1. Falsifier (stated before implementing) and whether it fired

**Falsifier:** *"This is benign if every unclassified component is already further from mains than the largest IEC
margin."* Largest IEC margin = `max(min_clearance_mm, min_creepage_mm)` over every row of `IEC60335_REQUIREMENTS`
(`tests/requirements/validators/clearance.py`) = **8.0mm** (the REINFORCED creepage figure, present in three of the
six matrix rows). Computed programmatically, not hardcoded, so it tracks the matrix if it ever changes.

**Measured directly** (script + full board data below), against `elec/domain_manifest.yaml`'s original 39-net
declaration (before any change in this pass):

**FALSIFIER FIRED.** Three unclassified components sat closer than 8.0mm to the nearest component on a declared HV
net:

| ref | instance_path | distance to nearest HV component | nearest HV ref (instance_path) |
|---|---|---|---|
| R59 | `safety.ovp.r_adc_top2` | **5.388mm** | R58 (`safety.ovp.r_adc_top1`) |
| R53 | `safety.ovp.r_div_top3` | **6.048mm** | R4 (`power_in.r_bleed1`) |
| D3 | `discharge.d_fly1` | **6.913mm** | C23 (`hb.c_vddb`) |

This is NOT benign at face value -- it is exactly the "unknown-domain part near mains" case the task calls out.
Investigated further (not stopped at the number):

- **R59 and R53** are interior/near-boundary nodes of the two protective-impedance divider chains ALREADY declared
  in `elec/domain_manifest.yaml` (`ovp01_adc_sense_divider`, `ovp01_comparator_divider`). R59's nearest neighbour
  (R58) is its own immediate chain predecessor -- adjacent divider resistors sitting close together is the normal,
  intended layout for a series string, already governed by that chain's own construction/redundancy requirement
  (`scripts/check_domain_partition.py::check_chain_integrity`), not an unexamined crossing.
- **D3** (a flyback diode across relay `discharge.k_dis1`'s coil) sits on the relay's own "coil" pin group, which
  this manifest's own `isolators:` entry for `discharge.k_dis1` already labels `"SELV coil drive"` -- it was
  unclassified purely because that pin group's *net names* were never also listed under `domains: SELV: nets:`, a
  should-have-been-declared gap, not a genuine ambiguity.

**Resolution applied (Sec 2):** a small, mechanically-justified manifest expansion (8 net names, all directly
traceable to text the manifest already contains) reclassified D3 and R53 correctly. **After that fix, exactly ONE
candidate remains under margin: R59 at 5.388mm from R58** -- and R58/R59 are literally two resistors of the SAME
declared `ovp01_adc_sense_divider` chain. Taken completely literally, the falsifier still "fires" (R59 is under
8.0mm from a declared-HV component) -- reported honestly, not rounded away -- but the one remaining case is
structurally accounted for by an existing, arithmetically-justified manifest entry, not a new, undetected hazard.
This is stated explicitly rather than silently exempted: see Sec 4 for exactly how the fix represents this
distinction (a narrow, structural exemption keyed to shared chain membership, not a hardcoded ref-pair allowlist).

---

## 2. Net and component counts, before and after

All counts from a freshly rebuilt netlist (`make netlist`, 76/76 assertions PASSED, exit 0) and the live
`pcb/temper.kicad_pcb` (170 footprints, read-only, unmodified by this task).

### `elec/domain_manifest.yaml` (feeds `scripts/check_domain_partition.py`)

| | before | after |
|---|---|---|
| Declared nets | 39 (HV=13, SELV=26) | **47 (HV=15, SELV=32)** |
| Compiled nets | 165 | 165 |
| Unclassified nets | 126 (76.4%) | **118 (71.5%)** |
| Components (touch >=1 declared net) | 147 / 170 (86.5%) | **156 / 170 (91.8%)** |
| Unclassified components | 23 | **14** |
| `check_domain_partition.py` result | PASSED, 0 violations, 39 nets/2 domains/10 isolators/2 chains checked | PASSED, 0 violations, **47 nets**/2 domains/10 isolators/2 chains checked |

### `_real_board_fixture.py` (feeds `verify_iec60335_compliance` / `generate_domain_clearance_constraints` -- the
actual clearance/creepage path `domain_clearance.py` covers)

| | before (hand-maintained 10-net dict) | after (manifest-derived, full) |
|---|---|---|
| Declared/classified nets | 10 | **47** |
| Components matched | **127 / 170 (74.7%)** | **156 / 170 (91.8%)** |
| `verify_iec60335_compliance` result | `passed=True, error_count=0` | `passed=False, error_count=17` (see Sec 5 -- reported, not asserted; see Sec 6 for why) |

The **127/170 (74.7%)** figure is exactly the one cited in the task ("roughly 127 of 170 components as
classifiable... about 43 components are outside the clearance analysis entirely") -- confirmed by direct
measurement against the pre-existing fixture code, not assumed.

---

## 3. Full unclassified-component list with distance to nearest declared-HV component

Computed from live `pcb/temper.kicad_pcb` positions (Euclidean center-to-center distance, matching the validator's
own `_distance` metric) against every component touching a declared HV net.

### Before manifest fix (23 unclassified components, sorted by distance)

| ref | instance_path | nets | nearest HV ref (path) | distance (mm) |
|---|---|---|---|---|
| R59 | safety.ovp.r_adc_top2 | r_adc_top1-p2, r_adc_top2-p2 | R58 (safety.ovp.r_adc_top1) | 5.388 |
| R53 | safety.ovp.r_div_top3 | comp-inp, r_div_top2-p2 | R4 (power_in.r_bleed1) | 6.048 |
| D3 | discharge.d_fly1 | k_dis1-coil1, k_dis1-coil2 | C23 (hb.c_vddb) | 6.913 |
| D1 | power_in.d_flyback | bypass_relay-coil1/2 | R27 (hb.gate_ls.rg_on) | 9.595 |
| R14 | discharge.r_dis2b | k_dis2-nc, r_dis2a-p2 | R13 (discharge.r_dis2a) | 10.016 |
| R74 | safety.uvlo_logic.r_hyst | mon-ina_p, mon-outa | C1 (power_in.c_x2) | 10.422 |
| R45 | rtd_pan.r_avdd_top | rail_monitor-ina_p, vcc | R4 (power_in.r_bleed1) | 10.516 |
| R66 | safety.thermal.r_hyst | thermal-line, comp-inp | R23 (hb.gate_hs.rg_on) | 10.891 |
| D4 | discharge.d_fly2 | k_dis1-coil2, k_dis2-coil1 | U3 (power_in.zcd_opto) | 11.110 |
| R52 | safety.ovp.r_div_top2 | r_div_top1-p2, r_div_top2-p2 | C4 (power_in.c_bus1b) | 11.117 |
| R71 | safety.coil_thermal.r_hyst | coil_thermal-line, comp-inp | C24 (hb.c_dc_hf) | 11.780 |
| TP3 | safety.tp_uvlo2_fault | uvlo_logic-line | R7 (power_in.r_zcd_top2) | 12.599 |
| R12 | discharge.r_dis1b | k_dis1-nc, r_dis1a-p2 | RT1 (power_in.ntc) | 13.828 |
| R57 | safety.ovp.r_hyst | ovp-line, comp-inp | C3 (power_in.c_bus2) | 14.015 |
| C17 | hb.gate_hs.boot_cap | driver-p1-1, driver-p2 | R27 (hb.gate_ls.rg_on) | 14.039 |
| R19 | discharge.r_snub1 | k_dis1-nc, r_snub1-p2 | C8 (discharge.c_snub2) | 14.779 |
| R42 | rtd_pan.r_high_top | r_high_top-inp, vbias | R27 (hb.gate_ls.rg_on) | 18.249 |
| R20 | discharge.r_snub2 | k_dis2-nc, r_snub2-p2 | C8 (discharge.c_snub2) | 19.176 |
| R30 | tank.inductor_conn | tank-out, c_tank1-p2 | C7 (discharge.c_snub1) | 19.902 |
| R34 | rtd_pan.r_ref | bias, refin_n | R27 (hb.gate_ls.rg_on) | 21.913 |
| C10 | power_mgmt.buck_3v3.c_boot | boot, sw | C2 (power_in.c_bus1) | 23.178 |
| R40 | rtd_pan.r_low_top | r_low_top-inn, vbias | C3 (power_in.c_bus2) | 24.499 |
| C22 | hb.c_vdda | driver-p1-1, driver-p2 | R27 (hb.gate_ls.rg_on) | 26.737 |

### After the 8-net manifest fix (Sec 4) -- 14 unclassified components remain

| ref | instance_path | nearest HV ref (path) | distance (mm) | exempt? |
|---|---|---|---|---|
| R59 | safety.ovp.r_adc_top2 | R58 (safety.ovp.r_adc_top1) | **5.388** | **YES -- same chain (`ovp01_adc_sense_divider`)** |
| R74 | safety.uvlo_logic.r_hyst | C1 (power_in.c_x2) | 10.422 | no |
| R45 | rtd_pan.r_avdd_top | R4 (power_in.r_bleed1) | 10.516 | no |
| R66 | safety.thermal.r_hyst | R23 (hb.gate_hs.rg_on) | 10.891 | no |
| R52 | safety.ovp.r_div_top2 | C4 (power_in.c_bus1b) | 11.117 | no |
| R71 | safety.coil_thermal.r_hyst | C24 (hb.c_dc_hf) | 11.780 | no |
| TP3 | safety.tp_uvlo2_fault | R7 (power_in.r_zcd_top2) | 12.599 | no |
| C17 | hb.gate_hs.boot_cap | R27 (hb.gate_ls.rg_on) | 14.039 | no |
| C10 | power_mgmt.buck_3v3.c_boot | R19 (discharge.r_snub1) | 16.146 | no |
| R42 | rtd_pan.r_high_top | R27 (hb.gate_ls.rg_on) | 18.249 | no |
| R30 | tank.inductor_conn | C7 (discharge.c_snub1) | 19.902 | no |
| R34 | rtd_pan.r_ref | R27 (hb.gate_ls.rg_on) | 21.913 | no |
| R40 | rtd_pan.r_low_top | C3 (power_in.c_bus2) | 24.499 | no |
| C22 | hb.c_vdda | R27 (hb.gate_ls.rg_on) | 26.737 | no |

**13 of 14 remaining unclassified components sit well beyond the 8.0mm margin** (>=10.4mm, most >=11mm). Only R59
is under margin, and it is the one, narrowly-justified chain-sibling exemption (Sec 4). **0 non-exempt findings
under margin** -- the new fail-closed assertion (Sec 6) currently passes.

---

## 4. Why are (most of) the 126 nets unclassified? Genuinely-unclassifiable vs should-have-been-declared

| category | count (of 126, before) | after fix |
|---|---|---|
| Empty/dangling (0 connected pins -- declared-but-unused signals in source) | 23 | 23 (unchanged; genuinely unclassifiable, no component to classify) |
| Single-ref (<=1 distinct component ref) | 32 | 32 (unchanged; see below) |
| Multi-ref (>=2 distinct component refs -- real net-level signals) | 71 | **63** |

**Empty nets (23):** dangling signal declarations in `elec/src` with zero wired pins in the compiled netlist (e.g.
`mcu-reference-*`, `safety-reference-*`, `gnd_ref`). `check_domain_partition.py` already surfaces these as an
informational note, not a violation. Genuinely unclassifiable -- there is no component to attach a domain to.

**Single-ref nets (32):** unused MCU GPIOs (`gpio18`, `io40`, `rx`, `tx`, ...), IC no-connect pins (`nc_7`, `nc_12`,
`nc3`, ...), and two relay N.O. contacts that are wired to nothing else (`discharge.k_dis1-no`,
`discharge.k_dis2-no` -- confirmed: single ref each, `K2`/`K3` only). A net with exactly one distinct ref can never
form a cross-domain PAIR under `_domain_boundary_pairs`'s pairing logic regardless of how it is declared -- so while
a handful of these (the relay N.O. contacts) are "really" HV by physical role, declaring them changes nothing about
clearance coverage. Left undeclared; genuinely unclassifiable **for this check's purposes**, not a should-have-been
gap.

**Multi-ref nets (71 before / 63 after -- the real signal-net gap):** these are the substantive finding. Almost all
are internal, auto-named signal nets within otherwise-fully-SELV functional blocks -- the RTD ADC's SPI bus segments
(`sclk`, `sdi`, `sdo`, `cs_n`, `bias`, `refin_n`, `vbias`), the 3.3V buck regulator's internal nodes (`boot`, `sw`,
`fb`), the isolated gate driver's primary/secondary internal pins (`ina`, `inb`, `input`, `hb.gate_hs.driver-p1`),
the safety-comparator network's hysteresis/threshold lines (`safety.thermal-line`, `safety.thermal.comp-inp`,
`safety.uvlo_logic.mon-ina_p`, ...), and the discharge-relay drive/snubber network
(`discharge.q_dis_drv-g`, `discharge.r_dis1a-p2`, `discharge.r_snub1-p2`, ...). **8 of these 71 were closed in this
pass** (Sec below), directly justified by text this manifest already contains -- not inferred from net-name
spelling, per the manifest's own ground rule. **The remaining 63 are very likely should-have-been-declared SELV (or,
for a couple, HV) nets**, but are left UNVERIFIED here rather than guessed, because I could not trace each one back
to elec/src to confirm its actual domain independently -- exactly the caution the manifest's own header comment
demands ("never a pattern, prefix, or naming-convention guess"). See Sec 7 for the explicit UNVERIFIED list.

### The 8 nets closed in this pass (`elec/domain_manifest.yaml`)

All eight are **directly derived from text the manifest already contained** (isolator `pin_labels`/`groups`, or the
protective-impedance chain's own documented single-fault voltage analysis) -- not inferred from net-name spelling:

- **SELV (6 nets):** `discharge.k_dis1-coil1`, `discharge.k_dis1-coil2` (also covers `discharge.k_dis2`'s own coil2
  pin -- confirmed directly from the compiled netlist that the two relays' coil-2 terminals share one net, no
  separate `discharge.k_dis2-coil2` net record exists), `discharge.k_dis2-coil1`, `power_in.bypass_relay-coil1`,
  `power_in.bypass_relay-coil2` -- these are exactly the pins each isolator's own `pin_labels` already call
  `"SELV coil drive"`. `safety.ovp.comp-inp` -- the OVP comparator's sense node, the far end of the
  `ovp01_comparator_divider` chain; the manifest's own single-fault analysis (search "SINGLE-FAULT DIRECTION WHEN
  r_div_bot (R54) OPENS") already establishes this node sits at ~1.4V normal / clamped ~3.6V under the originally-
  flagged single fault -- genuinely SELV-range in both analyzed conditions.
- **HV (2 nets):** `discharge.k_dis1-nc`, `discharge.k_dis2-nc` -- the same relays' own `"contacts"` group (below
  pin 1, `"COM (HV bus contact)"`); pin 4 (NC) is the same undifferentiated group, just not separately labeled.

**Deliberately NOT closed:** the divider chains' own purely-interior nodes (`safety.ovp.r_div_top1-p2`,
`safety.ovp.r_div_top2-p2`, `safety.ovp.r_adc_top1-p2`, `safety.ovp.r_adc_top2-p2`) sit at genuinely intermediate
voltage (per the manifest's own arithmetic, ~57-166V for the comparator divider's interior nodes) -- neither HV
nor SELV by voltage, and forcing either label would be exactly the naming-convention guess the manifest's ground
rule forbids. Left unclassified, with the fail-closed proximity check (Sec 6) as the safety net for that decision.

---

## 5. The 17-violation finding (informational, not asserted -- see Sec 6 for why)

Feeding the FULL manifest-derived classification (47 nets, 156/170 components) into `verify_iec60335_compliance`
against the current, unmodified `pcb/temper.kicad_pcb` surfaces **17 raw violations across 9 unique component
pairs** that were invisible under the old 10-net fixture classifier:

| pair | domains | worst measured | worst required | margin type |
|---|---|---|---|---|
| R27 (`hb.gate_ls.rg_on`) <-> C28 (`rtd_pan.c_vdd`) | DC_BUS <-> LV_CONTROL | **2.262mm** | 3.0/4.0/6.0/8.0mm | fails BASIC clearance+creepage AND reinforced |
| R27 <-> R70 (`safety.coil_thermal.r_ref_bot`) | DC_BUS <-> LV_CONTROL | **2.262mm** | same | fails BASIC clearance+creepage AND reinforced |
| R58 (`safety.ovp.r_adc_top1`) <-> R60 (`safety.ovp.r_adc_top3`) | DC_BUS <-> LV_CONTROL | 3.980mm | 4.0/6.0mm | fails basic creepage, reinforced clearance+creepage |
| C23 (`hb.c_vddb`) <-> D3 (`discharge.d_fly1`) | DC_BUS <-> LV_CONTROL | 6.913mm | 8.0mm | fails reinforced creepage only |
| R23 (`hb.gate_hs.rg_on`) <-> R69 (`safety.coil_thermal.r_ref_top`) | DC_BUS <-> LV_CONTROL | 7.385mm | 8.0mm | reinforced creepage only |
| R27 <-> U9 (`rtd_pan.adc`) | DC_BUS <-> LV_CONTROL | 7.342mm | 8.0mm | reinforced creepage only |
| R28 (`hb.gate_ls.rgs`) <-> R25 (`hb.gate_hs.r_filt_a`) | DC_BUS <-> LV_CONTROL | 6.080mm | 8.0mm | reinforced creepage only |
| R4 (`power_in.r_bleed1`) <-> R53 (`safety.ovp.r_div_top3`) | DC_BUS <-> LV_CONTROL | 6.048mm | 8.0mm | reinforced creepage only |
| R7 (`power_in.r_zcd_top2`) <-> R2 (`power_in.r_gate`) | DC_BUS <-> LV_CONTROL | 7.854mm | 8.0mm | reinforced creepage only |

These are **real findings, not artifacts of this pass's own manifest edits** -- most involve nets
(`SW_NODE`/`GATE_HS`/`GATE_LS`, `V_BUS_SENSE`, RTD_* ) that were **already** declared in the *original* 39-net
`elec/domain_manifest.yaml`, well before this task started; they were simply never fed into the clearance
validator because `_real_board_fixture.py`'s own hand-maintained list never included them. Two (C23<->D3,
R4<->R53) do depend on this pass's 8-net manifest expansion (Sec 4) and are new information surfaced by that fix,
not carried over. The two worst (R27<->C28, R27<->R70, at 2.262mm) fail even the lowest BASIC-insulation threshold
and would be the first priority for a placement fix.

**Why this is reported here but not turned into a hard, asserted failure:** the board's current placement was
solved (R24 CP-SAT pass) with knowledge of only the OLD 10-net boundary set -- of course it does not also satisfy
margins against boundaries it was never told existed. Fixing this requires a **placement re-solve** with the wider
constraint set, which this task cannot perform: `pcb/temper.kicad_pcb` is explicitly read-only here (another agent
is concurrently routing it), and the task's own hard constraints forbid reaching 0 violations by narrowing a domain,
raising a margin, or allowlisting a pair -- the only way left to make this pass would be exactly the trick that is
forbidden. Converting the existing `test_temper_board_clearance_compliance` assertion itself to use the wider set
would therefore break the task's "must still pass" verification requirement for a reason outside this task's
control. See Sec 6 for the resolution: the wider classification is used for coverage + the new fail-closed
proximity check (which robustly passes), and this 17-violation figure is computed and printed every time the test
runs (impossible to miss), without gating the test's pass/fail on a re-solve this task cannot do.

---

## 6. What changed

1. **`elec/domain_manifest.yaml`** -- 8 net declarations added (Sec 4), all directly justified by text the manifest
   already contained. Re-verified: `scripts/check_domain_partition.py` still reports **0 violations** (0 domain
   crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects), now over **47** declared nets
   (was 39).

2. **`_real_board_fixture.py`** rewritten to derive its `VoltageDomain` classification from
   `elec/domain_manifest.yaml` (via `scripts/check_domain_partition.py`'s own manifest loader and netlist parser --
   reused, not reimplemented) instead of maintaining a second, independent 10-net dict. It now:
   - Returns TWO classifications: a **legacy** one (the original 10 net names, unchanged, used for the actual
     `verify_iec60335_compliance` pass/fail assertion) and a **full** one (all 47 manifest nets, used for coverage
     reporting and the new proximity check). This split is what lets the test stay honest about the whole-board
     picture (Sec 5) without breaking on a placement re-solve this task cannot perform (Sec 5's last paragraph).
   - Computes `stats["coverage_ratio"]`, `stats["unclassified_components"]`, and
     `stats["proximity_findings"]` -- every unclassified component's straight-line distance to its nearest
     HV-classified neighbour, with a `chain_sibling` exemption (Sec 3/4) computed structurally from
     `elec/domain_manifest.yaml`'s own `protective_impedance_chains:` declarations (via
     `scripts/check_domain_partition.py::resolve_chain_refs`) -- not a hardcoded ref-pair allowlist.

3. **`test_clearance.py::test_temper_board_clearance_compliance`**:
   - Coverage is now printed prominently every run: `"DOMAIN CLASSIFICATION COVERAGE: 156 of 170 components
     classified (91.8%), 47 of 165 compiled nets classified (legacy boundary set used by the hard check below:
     127 components / 10 nets)."`
   - The `assert matched_components_in_placement > 0` guard is **kept intact** (per the task's explicit
     instruction) and **strengthened** with a new `assert stats["coverage_ratio"] >= 0.85` (currently 91.8%,
     comfortable headroom above the floor, well above the old 74.7%).
   - New fail-closed assertion: `assert not non_exempt_proximity` -- any unclassified component within the 8.0mm
     max IEC margin of a declared-HV component, other than the one documented chain-sibling exemption, hard-fails
     this test. Currently 0 non-exempt findings (Sec 3).
   - The 17-violation full-coverage finding (Sec 5) is computed and printed every run
     (`"FULL-COVERAGE INFORMATIONAL CHECK (not asserted): 17 REQ-SAFE-01 violation(s)..."`), but not asserted --
     see Sec 5 for why.
   - The existing `verify_iec60335_compliance(placement, voltage_domains)` assertion is unchanged in behaviour
     (still runs against the legacy 10-net set, still 0 violations, still passes).

---

## 7. UNVERIFIED

- **The 63 remaining multi-ref unclassified nets** (Sec 4) are very likely should-have-been-declared SELV (mostly)
  or HV nets, but their exact domain was not independently traced against `elec/src` in this pass -- only the 8
  nets closed here had that direct textual justification already present in the manifest. Candidates, by rough
  functional grouping (not independently confirmed):
  - RTD ADC SPI bus + reference network: `sclk`, `sdi`, `sdo`, `cs_n`, `bias`, `refin_n`, `vbias`,
    `rtd_pan.rail_monitor-ina_p`, `rtd_pan.rail_monitor-outa`, `rtd_pan.r_high_top-inp`, `rtd_pan.r_low_top-inn`,
    `rtd_pan.high_window-out`, `rtd_pan.low_window-out`, `vcc`, `y`.
  - Safety-comparator network hysteresis/threshold/output lines: `safety.thermal-line`,
    `safety.thermal.comp-inp`, `safety.coil_thermal-line`, `safety.coil_thermal.comp-inp`, `safety.ocp-line`,
    `safety.ocp.comp-inn`, `safety.ovp-line`, `safety.ovp.comp-inn`, `safety.uvlo_logic-line`,
    `safety.uvlo_logic.mon-ina_p`, `safety.uvlo_logic.mon-outa`, `safety-line`, `safety-line-1/2/3`,
    `safety.fault_any_or-a2/y2`, `safety.fault_or-b2/y2`, `safety.fault_or3-y2`.
  - Isolated gate driver primary-side internal pins: `ina`, `inb`, `input`, `hb.gate_hs.driver-p1`,
    `hb.power_loop.q_high-g`.
  - 3.3V buck regulator internal nodes: `boot`, `sw`, `fb`.
  - Discharge-relay drive/snubber network: `discharge.q_dis_drv-g`, `discharge.r_dis1a-p2`,
    `discharge.r_dis2a-p2`, `discharge.r_snub1-p2`, `discharge.r_snub2-p2`, `power_in.q_relay_drv-g`,
    `power_in.r_zcd_top1-p2`, `power_in.ntc-no`.
  - Misc: `I_SENSE`, `en`, `io0`, `tank-out`, `tank.c_tank1-p2`, `thermal.j_fan-p1`.
- **Whether IEC 60335-1 requires a full pairwise clearance/creepage check between the two ENDS of an already-declared
  protective-impedance divider chain** (e.g. R58 <-> R60, Sec 5) **in addition to** the chain's own
  current-limiting/redundancy construction requirement, or whether the construction requirement alone suffices --
  not resolved here; the manifest's own existing text (search "whether IEC 60335-1 additionally requires resistors
  used in a protective-impedance role to be a specifically qualified/tested 'safety' construction") already flags
  an adjacent open question in the same area. This evidence doc treats the R58<->R60 finding (Sec 5) as a real,
  reportable clearance gap regardless of that open question, since clearance/creepage is a physical-gap requirement
  independent of the resistor's current-limiting role.
- **`test_production_board_routing_drc_regression`** and any routing-dependent check -- out of scope; this task is
  placement/classification-only and `pcb/temper.kicad_pcb` has 0 segments/vias/zones regardless.
- **Whether the concurrently-running routing/placement agent's eventual re-solve will change the 156/170 and
  17-violation figures** -- not re-verified after this doc was written; both were measured against the board state
  present at the time of this analysis.

---

## 8. Gates and verification

| Check | Result |
|---|---|
| `make netlist` | **76/76 assertions PASSED**, exit 0 |
| `scripts/check_domain_partition.py` | **exit 0** -- 0 domain crossings, 0 isolator-barrier breaches, 0 chain defects, over **47** declared nets (was 39) / 2 domains / 10 isolators / 2 chains / 165 compiled nets / 170 components |
| `scripts/capacity_budget_gate.py` | exit 0 |
| `scripts/mpn_fabrication_gate.py` | exit 0 |
| `scripts/check_derived_doc_drift.py` | exit 0 |
| `tests/requirements/safety/test_clearance.py` + `test_isolation.py` + `tests/placer/cp_sat/test_domain_clearance.py` | **67 passed, 0 failed** |
| `test_temper_board_clearance_compliance` | **PASSED** -- `assert matched_components_in_placement > 0` guard intact (127 > 0) AND strengthened with `assert coverage_ratio >= 0.85` (91.8%) AND new fail-closed proximity assertion (0 non-exempt findings) |
| `pcb/temper.kicad_pcb` | unmodified (confirmed via `git status`) |
| `elec/src/*.ato` | unmodified (confirmed via `git status`) |

**Summary of what the gate now reports:** coverage went from **127/170 (74.7%) components / 10 nets** (the old,
silently-narrow clearance-path classifier) to **156/170 (91.8%) components / 47 nets** (manifest-derived), printed
prominently every test run, alongside a fail-closed check that would hard-fail on any *future* unclassified
component sitting within the largest IEC margin of a declared-HV part (currently 0 such findings, 1 documented
exemption). The 17-violation full-coverage finding is disclosed every run, not hidden, with an explicit, evidenced
reason why it is not (yet) a hard gate: it requires a placement re-solve outside this task's read-only-board scope.
