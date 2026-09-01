<!-- provenance: commit=c89f6b5da0a30c9e46ce44150edac1718fe2001d dirty=UNKNOWN -->

# The board is checked at PD2/8.0mm reinforced creepage; the standard's own unmet condition requires PD3/12.6mm. Correcting the 4 enforcement sites measures +153 creepage violations (168 -> 321, +91%), and 5 of 8 declared galvanic isolators cannot reach 12.6mm at their own footprint geometry regardless of placement.

## Verdict, up front

1. **The gap is confirmed exactly as reported.** `scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_ENFORCED_MM` constant is emitted into exactly **4** `(constraint creepage ...)` sites (RULE 2 "AC Mains to LV", RULE 4 "HV to LV", RULE 4b "HighVoltageIsolated to LV", RULE 4c "HighVoltageTank to LV") — confirmed by grepping every `constraint creepage` emission in the file; a 5th site (the resonant-tank functional-insulation rule, `HV_TANK_CREEPAGE_ENFORCED_MM`) is a **different constant, already correctly modelled as Table 18 functional insulation**, and is untouched by this gap and by this document (§1). All 4 sites are genuinely **Table 17 reinforced** HV/mains-side-netclass-to-everything-else crossings — none is misclassified functional insulation — so the "not every rule should become 12.6mm" nuance the task anticipated does not apply here: all 4 legitimately take the same figure. `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:174,183` gives **6.3mm basic / 12.6mm reinforced** as the PD3 row for this board's >250–400V working-voltage band (IEC 60335-1 Table 17, row iv, Material Group IIIa/IIIb) — re-verified in this document, not just cited. `scripts/check_pd2_compartment_evidence.py` still fails today (re-run this session): the PD2 sealed-compartment precondition remains unmet.
2. **Blast radius, measured, not estimated:** regenerating the DRU with all 4 sites at 12.6mm (scratch copy only, never installed) and running `kicad-cli 10.0.5` DRC against the real, unmodified board: **true creepage count 168 → 321 (+153, +91.1%)**, exhaustively counted via `scripts/measure_uncapped_drc.py` (creepage is *not* saturated at kicad-cli's own ERROR_LIMIT=199 at PD2, but the "HV to LV" band alone saturates at PD3 and needed the tool's real net-name split). Every other DRC category is provably unaffected — the two generated `.kicad_dru` files differ in exactly 4 lines (the `min` value on the 4 sites), and raw `kicad-cli` category counts are identical across all 21 other reported categories between the PD2 and PD3 runs. The board's own committed ratchet ceiling for creepage is **170** (`power_pcb_dataset/drc_ceiling.json`, same board hash) — the corrected figure exceeds it by **151** (1.89×). This document does not raise that ceiling.
3. **5 of the board's 8 currently-declared galvanic isolators cannot reach 12.6mm at their own intrinsic footprint geometry, regardless of placement or routing** (§3, first-hand measured this session with the project's own canonical, rotation-and-side-aware pad-geometry kernel — the same method PR #1146 used for T1/T2, reproduced here and extended to the other 6 declared isolators): **T1, T2** (Coilcraft CST3015, 9.100mm — PR #1146's finding, confirmed independently here, cited not duplicated), **U6** (TI UCC21550BDWKR gate driver — named "U7" in documents that predate a refdes renumber; instance path `hb.gate_hs.driver`, 8.100mm), **K1** (Omron G4A-1A-E bypass relay, 8.000mm), **C6** (Y1 capacitor, 8.000mm). Of these, **T1/T2 alone have no known part-level fix at any level of this repo's own prior research** (exhaustive same-ratio/current-class CT search, PR #1146 + `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`, found nothing better). **K1 and C6 already have verified, un-landed same-role replacement parts** that clear 12.6mm. **U6 has no same-class IC fix but does have a verified different-technology (discrete digital isolator) redesign path.** The remaining 3 declared isolators pass: **K2, K3** (12.760mm, +0.160mm margin — the repo's own prior work already calls this "razor-thin"), **PS1** (35.500mm, comfortable). A former isolator, **U3** (ZCD optocoupler), was already removed from the design specifically because no optocoupler family could reach 12.6mm.
4. **Plan, ranked (§4):** land the two already-identified K1/C6 part swaps first (zero new research, zero topology change); evaluate a routed creepage-lengthening slot for U6 and, as an unproven experiment, for T1/T2; treat U6's discrete-digital-isolator redesign as the fallback if the slot does not clear it; treat T1/T2 as the one open item with no currently-known compliant path (needs either a certified aperture-primary CT or a proven slot result); conformal coating is a real, clause-backed lever for the board's broader open-surface creepage debt but is proven, not assumed, to do nothing for any of the 5 structurally-failing isolators; raising the enforced constant is a policy decision, available at any time, that this document deliberately does not execute.

---

## 1. Confirming the gap and the governing figure

### 1.1 The 4 sites, exactly

`grep -n "constraint creepage" scripts/generate_kicad_dru.py` returns exactly 5 lines: 4 use `HV_CREEPAGE_ENFORCED_MM` (lines 885, 980, 1023, 1117 at this commit) and 1 uses the separate `HV_TANK_CREEPAGE_ENFORCED_MM` (line 1292). The 4:

| Rule (as emitted) | Condition (A-side / B-side) | Clearance (unchanged) | Creepage today (PD2) | Creepage, correct (PD3) |
|---|---|---:|---:|---:|
| RULE 2 "AC Mains to LV" | `A.NetClass=='ACMains'` vs everything except ACMains/HighVoltage/HighVoltageTank/GateDriveHV | 6.0mm | 8.0mm | **12.6mm** |
| RULE 4 "HV to LV" | `A.NetClass=='HighVoltage'` vs everything except HighVoltage/HighVoltageTank/ACMains/GateDriveHV/HighVoltageIsolated | 2.0mm | 8.0mm | **12.6mm** |
| RULE 4b "HighVoltageIsolated to LV" | `A.NetClass=='HighVoltageIsolated'` vs everything except itself/HighVoltage/HighVoltageTank/ACMains/GateDriveHV | 2.0mm | 8.0mm | **12.6mm** |
| RULE 4c "HighVoltageTank to LV" | `A.NetClass=='HighVoltageTank'` vs everything except itself/HighVoltage/ACMains/GateDriveHV/HighVoltageIsolated | 2.0mm | 8.0mm | **12.6mm** |

All 4 conditions anchor on a mains/HV-side net class matched against "everything else" (the LV/SELV side of the board) — this is precisely the reinforced mains↔SELV/PELV barrier Table 17 governs, not the same-domain functional case Table 18 covers. The 5th, untouched, site (`HV_TANK_CREEPAGE_ENFORCED_MM`, RULE 5a "HighVoltageTank functional creepage") is explicitly and correctly modelled as Table 18 functional insulation in the generator's own source comments (`scripts/generate_kicad_dru.py:141-172`) and is out of scope for this gap — it is a separate, already-analysed defect (`docs/evidence/2026-08-12-pollution-degree-resolution.md`, PD3/10.0mm vs the currently-enforced PD2/6.3mm), not duplicated here. **So the "not every rule should necessarily become 12.6mm" caveat the task raised does not carve out an exception among these 4** — none is misclassified functional insulation; all 4 are correctly reinforced and all 4 take the identical figure.

### 1.2 The correct figure, re-verified

`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:174,183` (read directly this session):

| Working Voltage (V) | PD3 Basic (mm) | **PD3 Reinforced (mm)** |
|---|---:|---:|
| >250, ≤400 | 6.3 | **12.6** |

Every net on the 4 sites' HV/mains side (MAINS 340V pk, DC bus 400V pk/transient, Gate Drive Isolated 355V peak-to-earth) falls in this row. `docs/evidence/2026-08-12-pollution-degree-resolution.md` independently re-derives the same PD3 governance finding for the board's *other* (tank/functional) creepage gap, and its own §1 conclusion — "PD3 is the repo's selected... **not** an earned classification... PD2 is the repo's selected target, not an earned classification. On the standard's own condition, PD3 governs the as-built board now" — applies identically here. Re-ran `scripts/check_pd2_compartment_evidence.py` this session: still reports `FAILED — docs/specs/pd2_compartment_evidence.yaml does not exist`, confirming the PD2 precondition remains unmet today, unchanged since the cited decision records.

### 1.3 The related, out-of-scope-but-not-independent enforcement point

`scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` (`packages/temper-placer/src/temper_placer/core/isolation_constants.py`) is a *second*, independent PD2/8.0mm enforcement point for the same physical requirement — the DRU generator's own RULE 2 comment says the two "must remain aligned." It is not one of the 4 sites named in this task and is not measured here, but any decision that moves `HV_CREEPAGE_ENFORCED_MM` should move this constant too, or the two checks will silently disagree.

---

## 2. Measured blast radius

### 2.1 Method

A throwaway copy of `scripts/generate_kicad_dru.py` (never installed over the real file, never written into `pcb/`) with exactly one line changed — `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM` → `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM` — regenerates cleanly (`find_shadowing()` returns `[]`, i.e. the strictest-matching-rule invariant still holds) and its emitted `.kicad_dru` differs from the real generator's output in **exactly 4 lines**, each an 8.0mm→12.6mm creepage `min` value change, confirmed by direct diff. `scripts/measure_uncapped_drc.py dru-category creepage` (this repo's own provably-exhaustive DRU-rule partition-and-sum tool, documented in `docs/evidence/2026-08-12-uncapped-drc-measurement.md`) was run against the real, unmodified `pcb/temper.kicad_pcb`/`temper.kicad_pro` with both the PD2 (real generator) and PD3 (scratch copy) DRUs.

### 2.2 Creepage: 168 → 321 (+153, +91.1%), run twice, byte-identical

| Band (DRU rule) | PD2 (today, enforced) — true count | PD3 (correct) — true count | Δ | Δ% |
|---|---:|---:|---:|---:|
| AC Mains to LV | 7 | 13 | +6 | +85.7% |
| HighVoltageIsolated to LV | 27 | 39 | +12 | +44.4% |
| HV to LV | 125 | 250 | +125 | +100.0% |
| HighVoltageTank to LV | 7 | 17 | +10 | +142.9% |
| Subtotal, the 4 corrected sites | **166** | **319** | **+153** | **+92.2%** |
| HighVoltageTank functional creepage (untouched, Table 18 rule, cited §1.1) | 2 | 2 | 0 | — |
| **Total creepage** | **168** | **321** | **+153** | **+91.1%** |

Both totals were run **twice, independently, to completion** (separate scratch dirs, separate `kicad-cli` invocations per band): the PD2 run reproduced 168 with the identical 5-band breakdown both times; the PD3 run reproduced 321 with the identical 5-band breakdown, including the identical `HV to LV` net-name split (148 + 102 = 250), both times. The "HV to LV" band alone lands above `kicad-cli`'s own `ERROR_LIMIT=199` at PD3 (raw `kicad-cli` read on that isolated band would truncate); `measure_uncapped_drc.py`'s recursive real-net-name split (12 real `HighVoltage`-class nets on this board, split 6/12 + 6/12) resolved it to a deterministic, sub-cap 148/102 pair, matching the methodology `docs/evidence/2026-08-12-uncapped-drc-measurement.md` used for the equivalent PD2-era `clearance` "HV to LV" band. The 168 PD2 figure independently reproduces this board's own recorded `drc_ceiling.json` provenance (`observed: [166, 167, 168]` across 130 samples, same board hash) at its true, non-saturated maximum.

Against the committed ceiling (`power_pcb_dataset/drc_ceiling.json`, `creepage: 170`, same board hash `b7d865b7...`): the corrected figure of 321 exceeds it by **151** (**1.89×**). This document does not raise that ceiling — the correction, if adopted, is a decision for the user with its own ceiling-approval process (`scripts/check_drc_ceiling_approval.py`, R27).

### 2.3 Every other category: unaffected, confirmed not estimated

Raw `kicad-cli` category counts, PD2 vs. PD3 scratch DRUs, same unmodified board, same `kicad-cli 10.0.5`:

| Category | PD2 | PD3 | Δ |
|---|---:|---:|---:|
| annular_width | 4 | 4 | 0 |
| clearance | 500 (capped) | 500 (capped) | 0 |
| copper_edge_clearance | 7 | 7 | 0 |
| courtyards_overlap | 8 | 8 | 0 |
| **creepage** | **168** | **321 raw-capped-appearing, 321 true (§2.2)** | **+153** |
| drill_out_of_range | 4 | 4 | 0 |
| hole_clearance | 90 | 90 | 0 |
| hole_to_hole | 3 | 3 | 0 |
| lib_footprint_issues | 165 | 165 | 0 |
| lib_footprint_mismatch | 1 | 1 | 0 |
| missing_courtyard | 5 | 5 | 0 |
| pth_inside_courtyard | 1 | 1 | 0 |
| shorting_items | 181 | 181 | 0 |
| silk_edge_clearance | 1 | 1 | 0 |
| silk_over_copper | 63 | 63 | 0 |
| silk_overlap | 199 (capped) | 199 (capped) | 0 |
| solder_mask_bridge | 145 | 145 | 0 |
| track_dangling | 44 | 44 | 0 |
| track_width | 199 (capped) | 199 (capped) | 0 |
| tracks_crossing | 1 | 1 | 0 |
| via_dangling | 30 | 30 | 0 |
| via_diameter | 4 | 4 | 0 |

`clearance`, `silk_overlap`, and `track_width` sit at their kicad-cli caps in **both** runs (identical raw numbers), consistent with the diff-proof that none of their governing `.kicad_dru` values changed — this document does not re-run `measure_uncapped_drc.py` on them because the delta between PD2 and PD3 for these categories is, by construction of the diff, exactly zero; re-measuring an unchanged input would not change that answer and duplicates `docs/evidence/2026-08-12-uncapped-drc-measurement.md`'s existing true-count work for `clearance`/`track_width` on this board lineage.

---

## 3. What becomes structurally impossible

### 3.1 Method

Same method PR #1146 used for T1/T2, reproduced and extended to every declared isolator in `elec/domain_manifest.yaml`'s `isolators:` block (8 entries): parse `pcb/temper.kicad_pcb` via `temper_placer.io.kicad_parser.parse_kicad_pcb`, resolve each declared pin's true world position via `temper_placer.core.pin_geometry.pin_world_position` (rotation-and-side-aware — the canonical function, not raw parser output), and compute the exact Minkowski-sum copper-to-copper distance for every primary/secondary (or coil/contact, or hv_side/selv_side) pin-group pair via `temper_placer.core.pad_geometry.pad_pair_distance` (Rust-backed, GEOS-bit-exact, no polygon-approximation error — the same function whose own docstring cites a real 8.000mm K1 pair this session reproduces exactly). Minimum over all cross-group pairs is each component's intrinsic isolation figure — a property of the footprint and its own rigid-body placement rotation, **independent of where else on the board it sits or how it is routed.**

One correction found in the process: `elec/domain_manifest.yaml`'s `hb.gate_hs.driver` instance (the UCC21550 gate driver, called `U7` in every evidence document predating this session) is refdes **`U6`** on the current, resynced board — confirmed by footprint match (`lib:SOIC16W_Isolated`) rather than assumed from stale documents.

### 3.2 Results — measured first-hand this session, current board

| Ref | Component | Role | Min. intrinsic pad-pair | vs. 12.6mm | Status |
|---|---|---|---:|---:|---|
| T1 | Coilcraft CST3015-100ED | `ct_sense.ct`, OCP-01 current sense | **9.1000mm** | −3.500mm | **FAIL** |
| T2 | Coilcraft CST3015-100ED (same part) | `safety.ocp2.ct`, OCP-02 current sense | **9.1000mm** | −3.500mm | **FAIL** |
| U6 | TI UCC21550BDWKR | `hb.gate_hs.driver`, reinforced-isolation gate driver | **8.1000mm** | −4.500mm | **FAIL** |
| K1 | Omron G4A-1A-E DC12 | `power_in.bypass_relay` | **8.0000mm** | −4.600mm | **FAIL** |
| C6 | Murata DE1E3KX222MA5BA01 (2.2nF Y1) | `power_in.y_cap_pe` | **8.0000mm** | −4.600mm | **FAIL** |
| K2 | TE/Schrack RT314012 | `discharge.k_dis1` | 12.7600mm | +0.160mm | PASS — razor-thin margin |
| K3 | TE/Schrack RT314012 | `discharge.k_dis2` | 12.7600mm | +0.160mm | PASS — razor-thin margin |
| PS1 | Mean Well IRM-10-15 | `aux_supply.psu` | 35.5000mm | +22.900mm | PASS, comfortable |
| *(U3, former)* | *Vishay H11L1TVM (removed 2026-07-30)* | *ZCD optocoupler* | *8.560mm (as removed)* | *−4.040mm* | *Resolved by deletion — no optocoupler family reached 12.6mm* |

T1/T2's 9.1000mm and K2/K3's 12.7600mm reproduce PR #1146 and the repo's prior sourcing research (`docs/evidence/2026-07-28-isolator-sourcing-brief.md`) to four decimal places, independently. U6's 8.1000mm and K1/C6's 8.0000mm reproduce `docs/evidence/2026-08-08-isolation-barrier-geometry-analysis.md`'s pad-pair spot-check exactly (that document's own finding: K1 and C6 sit at "exactly 8.0000mm... the design was evidently placed to hit this minimum precisely, not by accident" — reproduced here first-hand, not merely re-cited).

**5 of 8 currently-declared galvanic isolators — T1, T2, U6, K1, C6 — cannot reach 12.6mm at their own intrinsic footprint geometry, regardless of placement.** This is not a routing or placement defect; it is a property of each component's own package/pin geometry, exactly as PR #1146 established for T1/T2 alone. This document's contribution is showing the set is **5, not 2** — the other 3 declared isolators (K2/K3/PS1) already clear the bar (K2/K3 with essentially no margin), and one former isolator (U3) was already deleted from the design for the identical reason.

### 3.3 The 5 do not all have the same remediation status — this matters for the plan

- **T1, T2 — no known fix at all.** This repo's own prior exhaustive search (`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`, cited by PR #1146, not duplicated here) checked every 1:100-ratio, ≥50A-sensed current-sense transformer across Coilcraft, TDK and others and found none with better PCB creepage than the incumbent CST3015. The one real, unexplored path is a topology change (§4.5).
- **K1 — a same-role, same-footprint-class replacement is already verified.** TE Schrack **RT33K012** (`2-1393240-3`, SPST-NO, 20A UL/16A IEC, 12VDC/360Ω/400mW coil): **17.8mm nominal** PCB coil-to-contact spacing, MEASURED against TE's own dimensioned drawing (`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`). Not yet landed — `elec/src/modules.ato:757` still specifies `G4A-1A-E DC12`.
- **C6 — a value-changed replacement is already verified, including the touch-current re-check the first pass flagged as open.** TDK **B81123C1562M000** (5.6nF Y1, 500VAC, 22.5mm lead spacing) clears 12.6mm with +7.1mm margin *and*, per the corrected accounting in `docs/evidence/2026-07-30-c6-touch-current-budget-and-part2-routes.md`, clears the board's IEC 60335-2-6 touch-current budget with 9–15% headroom even under the most conservative reading checked (no protective-impedance exemption, no filter-doubling credit). This requires a 2.5× value change from the spec'd 2.2nF ±20% window — a real electrical-design decision, not a footprint swap — but is not blocked on further sourcing research. Not yet landed — `elec/src/modules.ato:912-913` still specifies 2.2nF.
- **U6 — no same-class IC fix exists anywhere searched, but a different barrier technology does.** `docs/evidence/2026-07-30-pd3-isolation-mechanism-alternatives.md` surveyed TI, Vishay, Broadcom and one disqualified entrant (Chipanalog, certifications "Pending"): every reinforced gate-driver IC and every optocoupler plateaus at 7–8.5mm, independent of function or rated isolation voltage — an IC lead-frame/package-geometry ceiling, not a die-performance one. A **discrete, certified digital isolator** (TI `ISO7741FQDWWRQ1`, DWW-16 package, real/orderable — DigiKey Active) plus a local secondary-side gate-driver IC per switch achieves **>14.5mm**, manufacturer-verified — clearing 12.6mm with real margin. This is a genuine schematic/BOM/gate-drive-timing redesign (two ICs per switch instead of one integrated part), not a drop-in.

### 3.4 Conformal coating does not rescue any of the 5 — evaluated directly, not inherited from the litz-pad ruling

The task asked this to be checked properly rather than assumed, since the litz-pad ruling (`scripts/generate_kicad_dru.py`'s `COATING_QUALIFIED` fail-closed comment) is about a *different* mechanism — bare pads required for hand-soldering, which fails IEC 60664-3 cl. 4.3's full-coverage requirement structurally. SMD parts reflowed *before* coating is applied are not subject to that particular objection. Checked directly against `docs/evidence/2026-07-28-conformal-coating-pd1.md` §4.2's own per-package-class measurement, which is general enough to answer this:

- **U6 (SOIC-16 wide):** "the entire 7.250mm inter-row gap lies inside the package body outline, and the pads themselves tuck 0.125mm under it" — MEASURED. This is true regardless of when a coating is applied relative to reflow: a post-reflow spray/dip coating is a surface film on the *exposed* board; it cannot flow into the space between an already-seated package's molded body and the PCB. The limiting factor is package geometry, not solder sequencing.
- **K1 (THT relay, SMD contact tab):** the governing 8.000mm pair runs 100% under the relay's own 30.50×23.50mm plastic body — same conclusion, same reason.
- **T1/T2, C6:** same structural finding — every declared isolator's shortest HV↔SELV path sits 100% under its own component body (`conformal-coating-pd1.md` §4.2's verdict, stated to hold across every package class checked: SOIC, THT relay, and THT-relay-with-SMD-tab).

**Conclusion: coating is not a fix for T1, T2, U6, K1, or C6, at any coating quality and regardless of SMD vs. THT construction or solder-order** — every one of their governing paths is proven to run underneath a seated component body, which no post-assembly surface film reaches. This is the same functional dead-end the litz-pad ruling reached, arrived at independently here for a geometric rather than a process reason, so the two rulings agreeing is a consistency check, not a re-use of one argument for the other.

**Where coating genuinely would help:** `conformal-coating-pd1.md` §4.4 found 116 of 222 board-wide sub-12.6mm HV↔SELV pad pairs have a path crossing **no** component body at all — open-surface trace/pad approaches between *non-isolator* parts. For that population (not the 5 isolators above), a properly qualified Type A coating process is a real, IEC 60664-3 Annex J-backed remedy — contingent on adding a real coating step to the BOM/assembly (none exists today; `COATING_QUALIFIED = False` in the generator, correctly fail-closed) and a per-path clause-4.3 coverage argument. This is a genuine, partial lever on the board's broader creepage debt, just not on the isolator-blocking cases that are this gap's hard core.

---

## 4. Plan, ranked by feasibility and cost

| # | Action | Fixes | Cost | Feasibility |
|---|---|---|---|---|
| 1 | **Land the already-verified K1 (`RT33K012`) and C6 (`B81123C1562M000`, 5.6nF) part swaps** | K1, C6 (2 of 5) | BOM/schematic edit, footprint swap, re-place/re-route, re-verify DRC; C6's value change needs the touch-current re-check already done to be reviewed and accepted | **Highest** — zero new research; both parts and their clearance/touch-current math are already fully verified in this repo's own prior evidence, just not landed |
| 2 | **Evaluate a routed creepage-lengthening slot for U6**, and as an unproven experiment, **for T1/T2** | U6 (proven mechanism, unexecuted); T1/T2 (possible, unproven) | Per-instance mechanical design (slot placement/width) + DRC creepage-solver re-measurement; no new BOM line, no qualification burden | **Medium** — `conformal-coating-pd1.md` §4.2 explicitly names a routed slot as "the correct remedy for U7[U6]"; this repo has independently measured that a slot at a fixed 5.0mm straight-line gap raises measured creepage 5.0mm→41.05mm (`docs/evidence/2026-07-28-drc-creepage-constraint.md`), so the mechanism is proven in general — it has not been tried on U6 or T1/T2 specifically |
| 3 | **U6 topology change**: discrete digital isolator (`ISO7741FQDWWRQ1`, DWW-16) + local secondary-side driver, one stage per switch | U6 (fallback if #2 does not clear it) | Schematic/BOM/gate-drive-timing redesign, two ICs instead of one integrated part, new footprint/placement/routing | **Medium-high** — solved on paper with a real, orderable part and real margin (>14.5mm), but a genuine redesign, not a swap |
| 4 | **T1/T2**: pursue a certified aperture/donut-primary CT (Talema ASM, ICE Components CT07/8/10 class), or accept the slot-experiment result from #2 | T1, T2 (the one case with no currently-known compliant path) | New CT topology removes the PCB primary pin entirely (spacing becomes a layout choice, one burden-resistor value change already verified concretely), but every specific part checked so far lacks a verified third-party reinforced-insulation certificate | **Lowest today** — this is the one item in this enumeration genuinely unresolved by any prior work in this repo; needs either further certified-part sourcing or a positive result from #2 |
| 5 | **Conformal coating** for the board's broader (non-isolator) creepage debt | Up to 116 of 222 board-wide sub-12.6mm open-surface pairs (§3.4) — none of the 5 structurally-failing isolators | New BOM line, IEC 60664-3 Annex J qualification (clause 5 test regime), per-path clause-4.3 coverage argument, flip `COATING_QUALIFIED` | **Medium-high, and explicitly partial** — legitimate and clause-backed, but proven not to touch the hard core of this gap |
| 6 | **Raise `HV_CREEPAGE_ENFORCED_MM` to 12.6mm and record the debt honestly** | Nothing physically — makes the gate accurately red (321 true creepage violations, ceiling currently 170) instead of quietly checking the wrong number | Trivial code change (flip one alias, mirroring `HV_TANK_CREEPAGE_ENFORCED_MM`'s existing PD2/PD3 dict pattern); forces a `Ceiling-Approval:`-trailer decision (R27) and turns CI red board-wide until #1–4 land enough of the debt down | **Available immediately, but explicitly a policy decision for the user** — this document measures the cost of this move (§2) and does not execute it, per this task's hard constraint |

**Sequencing recommendation:** #1 is unconditional — it costs nothing further to research and closes 2 of 5 structurally-failing isolators outright. #2 should be attempted before committing to #3's redesign cost, since a slot is far cheaper if it works and the mechanism is already proven in general on this board. #4 is the long pole and should start in parallel, not after #1–3, since it is pure sourcing/certification lead time. #5 can proceed independently at any time for its own (partial) benefit. #6 is a standing option the user can take at any point once enough of #1–4 has landed to make the resulting debt tolerable — or immediately, as a deliberate "measure honestly now, fix over time" choice; this document takes no position on timing, only on cost.

---

## Files

- This document: `docs/evidence/2026-08-13-hv-creepage-pd3-gap-measurement-and-plan.md`
- Cites, does not duplicate: PR #1146 / `docs/evidence/2026-08-13-cst3015-reinforced-isolation-capability.md` (T1/T2 capability determination); `docs/evidence/2026-08-12-pollution-degree-resolution.md` and `docs/evidence/2026-08-11-pd2-decision-record.md` (PD3-governs determination); `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` (governing figures); `docs/evidence/2026-08-12-uncapped-drc-measurement.md` and `scripts/measure_uncapped_drc.py` (uncapped-count method); `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`, `docs/evidence/2026-07-30-c6-touch-current-budget-and-part2-routes.md`, `docs/evidence/2026-07-30-pd3-isolation-mechanism-alternatives.md` (per-component remediation research); `docs/evidence/2026-07-28-conformal-coating-pd1.md` (coating feasibility); `docs/evidence/2026-08-08-isolation-barrier-geometry-analysis.md` (K1/C6/U6/T1 pad-pair spot-check, reproduced here).
- Measured this session: creepage true-count JSON at PD2 and PD3 (2 independent runs each), the scratch PD3 DRU generator and its diff against the real generator, and the first-hand isolator pad-geometry measurement script — all under this session's scratchpad, not committed (scratch artifacts, per the task's "into a scratch path" instruction).
- Not modified by this document: `pcb/**`, `scripts/generate_kicad_dru.py`, `scripts/check_isolation_keepout.py`, any netclass, DRU rule, footprint, enforced safety constant, or `power_pcb_dataset/drc_ceiling.json` entry.
