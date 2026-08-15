<!-- provenance: commit=8f21d2725 (base of branch chore/cert-lab-package-review, = origin/main at the
     fork point of this finalizing branch; package drafted 2026-08-14 on cert-lab-package @ 5408cb275,
     reviewed and corrected 2026-08-15 — see "Review corrections" note at the end of Sec 2.5)
     dirty=false at time of writing. Own git worktree (/tmp/opencode/agent-cert-lab),
     never the main checkout and never .claude/worktrees/agent-a374c69e35366ad12. No pcb/temper.kicad_pcb,
     footprint, DRU threshold, or enforced safety constant was edited by this document or its companion
     commits (only the two stale ADUM1250 rows in docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md were marked
     superseded, documentation-only — see Sec 2.6 Q4). This package draws on work from FIVE branches;
     every figure below states which one it came from, and whether that branch is merged to `main`.
     See Sec 0 for the full map before using any number in this document. -->

# Certification-lab question package: PD3 island-slot creepage credit (T1/T2/U6) and IEC 60664-4 applicability at 44-50kHz

**Date:** 2026-08-14
**Purpose:** Two independent, in-house investigations this project cannot close without primary
standards text or a certification-lab determination have converged on the same class of problem —
neither is resolvable from any source available inside this repository. This package puts both to a
test house / certification body performing IEC 60335-1 review, in one pass, with enough evidence
attached that no follow-up round should be needed.

**Non-negotiable framing, stated up front:** nothing in this package invents, reconstructs,
interpolates, or estimates a standards value. Every clearance/creepage/voltage figure below is either
(a) quoted verbatim from primary standards text already recovered into this repository and cited by
exact location, or (b) measured directly against the real, committed board or a live circuit
simulation, with the method stated. Where a figure could not be sourced, this document says so
explicitly rather than filling the gap.

---

## 0. Provenance map — which branch every figure in this package lives on

This package was assembled from evidence spread across branches that have diverged from `main` in
different directions. **Read this section before citing any number from this document elsewhere.**

| Source document | Branch | Merged to `main`? | Used for |
|---|---|---|---|
| `docs/evidence/2026-08-12-hv-clearance-adequacy.md` | `main` (landed via PR #1080, commit `9187aab62`) | **Yes** | Question B: clearance derivation, 923.7V peak figure, OCP-01 margin analysis, IEC 60664-4 gap |
| `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` | `main` (landed via PR #1081, commit `c2b03fb23`) | **Yes** | Question B: clause 29.2.4 functional-insulation exemption analysis, Table 18 comparison |
| `docs/evidence/2026-07-28-conformal-coating-pd1.md` | `main` | **Yes** | Question B: IEC 60335-1 Annex J partial-discharge note (CITED-PRIMARY) |
| `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` | `main` | **Yes** | Both questions: IEC 60335-1 Tables 15/16/17, clauses 29.1/29.1.3/29.1.5 (CITED-PRIMARY) |
| `docs/evidence/2026-08-11-pd2-decision-record.md`, `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` | `main` | **Yes** | Both questions: PD3-governs-as-built finding |
| `docs/evidence/2026-08-13-hv-creepage-pd3-gap-measurement-and-plan.md` (PR #1152) | `analysis/hv-creepage-pd3-gap`, commit `02b27e3ef` | **No** | Question A: T1/T2/U6 intrinsic (unslotted) creepage baseline (9.100mm / 8.100mm) |
| `docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md` (PR #1155) | `analysis/slot-creepage-rescue`, commit `b0f0dc806` | **No** | Question A: original island-slot designs for T1/T2/U6 |
| `docs/evidence/2026-08-13-hv-creepage-island-slot-and-t1-structural-determination.md` (PR #1160) | `analysis/creepage-island-t1-structural`, commit `d1d6af050` | **No** | Question A: minimized T1 slot, the standards-gap analysis, the drafted lab question this package refines |
| `docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md` (this session) | `analysis/edge-slot-through-cut-rescue`, commit `103bb653c` | **No** | Question A: edge-reaching redesign, the Jordan-curve argument, computational verification |

**Board-state split, and why it matters.** Question B's figures were measured against the board at
sha256 `6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64` — the state currently on
`main` and on this package's own branch. Question A's figures were measured against a **different**
board state, sha256 `b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6`, reached via an
unmerged resync/designator-renumber commit (`96ebe489c`, on the `analysis/edge-slot-through-cut-rescue`
lineage, itself based on `origin/fix/board-schematic-resync` — **also not on `main`**). The two board
states are not interchangeable. Do not mix a Question A geometry figure with a Question B net-name
lookup against `main`'s `pcb/temper.kicad_pcb` without checking which state you're in.

**The one naming collision this causes, stated as plainly as possible:** on the branches Question A's
figures come from, reference designator **`U6` names the TI UCC21550BDWKR isolated gate driver**
(`hb.gate_hs.driver`), confirmed by footprint match. On `main` (and this package's own branch), that
renumber has not happened: **`main`'s `U6` is a TO-247-3 IGBT** (`hb.power_loop.q_low`), an unrelated
part, and **the UCC21550 gate driver is `U7` on `main` today**. Every "U6" in Question A below means the
gate driver, per the branch its figures are measured on — never the IGBT. If you hand this package's
Question A section to a lab together with `main`'s board file, translate `U6`→`U7` first or supply the
branch-specific board file instead.

**PR #1178** (a 6-layer stackup declaration cited in passing by the edge-reaching-slot document's
routing-cost section, §5 of that document) **has also not merged to `main`** — noted for completeness;
this package does not depend on it.

---

## 1. Question A — does a bounded (island) or edge-reaching PCB slot earn creepage credit at its closed end, for T1, T2, and U6?

### 1.1 Why this question, and why now

`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` and `docs/evidence/2026-08-11-pd2-decision-record.md`
(both on `main`) establish that **PD3 governs the as-built board today**: the design's chosen
production architecture is PD2 (8.0mm reinforced creepage), conditional on a sealed, gasketed PCB
compartment separate from the coil/heatsink forced-air path — but `scripts/check_pd2_compartment_evidence.py`
exits 3 (no compartment evidence committed) because the board is currently forced-air-vented with zero
vent/compartment provisions anywhere in the committed design. Until that compartment is built and
verified, **PD3's 12.6mm reinforced-creepage figure is the applicable requirement**, not PD2's 8.0mm.

At PD3, three of this board's declared galvanic isolators cannot reach 12.6mm from their own intrinsic
footprint geometry alone, regardless of placement or routing — this is a property of each part's
package/pin geometry, not a layout defect (`docs/evidence/2026-08-13-hv-creepage-pd3-gap-measurement-and-plan.md`
§3, branch `analysis/hv-creepage-pd3-gap`, not on `main`):

| Component | Part | Boundary | Intrinsic (unslotted) creepage | PD3 requirement | Shortfall |
|---|---|---|---:|---:|---:|
| **T1** | Coilcraft CST3015-100ED, current-sense transformer, `ct_sense.ct` | Primary (HV tank-loop current) ↔ secondary (OCP-01 SELV sense signal) | **9.100mm** | 12.6mm | **−3.500mm** |
| **T2** | Same part, same footprint, `safety.ocp2.ct` (OCP-02) | Same | **9.100mm** (if placed — see §1.5) | 12.6mm | **−3.500mm** |
| **U6*** | TI UCC21550BDWKR, isolated gate driver, `hb.gate_hs.driver` | Primary (SELV control) ↔ secondary (floats on `SW_NODE`, HV) | **8.100mm** | 12.6mm | **−4.500mm** |

*\*Designator per §0's naming note — this is `U7` on `main`.*

Both figures reproduce an earlier determination (PR #1146, cited but not duplicated by PR #1152) to
four decimal places, using this repo's own canonical rotation-and-side-aware pad-geometry kernel
(`temper_placer.core.pin_geometry.pin_world_position` + `pad_geometry.pad_pair_distance`, Rust-backed,
GEOS-bit-exact — no polygon-approximation error).

**Worth noting: this problem is contingent on PD3 governing.** At PD2's 8.0mm figure, T1/T2 (9.100mm)
already clear the requirement unslotted with +1.100mm margin, and U6 (8.100mm) clears it unslotted
too, though by only +0.100mm — a near-zero margin worth someone's separate attention even at PD2. If
the sealed compartment lands and PD2 is verified, this entire slot-credit question becomes moot for
these three components (though not for the rest of the board's broader PD3 creepage exposure, which
is out of scope for this package).

No part-level fix is known for T1/T2: an exhaustive search across Coilcraft, TDK, and other
manufacturers for any 1:100-ratio, ≥50A-sensed current-sense transformer with better PCB creepage than
the incumbent CST3015 found none (`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`, cited by
PR #1152). U6 has no same-class IC fix either — every reinforced gate-driver IC and optocoupler
surveyed (TI, Vishay, Broadcom) plateaus at 7–8.5mm, a package/lead-frame-geometry ceiling — but does
have a verified fallback: a discrete digital isolator (TI `ISO7741FQDWWRQ1`, DWW-16, real/orderable)
plus a local secondary-side gate driver IC per switch, manufacturer-rated >14.5mm, though this is a
genuine two-IC schematic/BOM/gate-drive-timing redesign, not a drop-in.

A routed creepage-lengthening slot is the one mechanism that reaches 12.6mm without a part change or
redesign — **if it earns the credit the standard's text does not clearly grant.**

### 1.2 The precise question(s) to ask the lab

> **Primary question.** For a fully-through, full-board-thickness, non-plated PCB slot that terminates
> *inside* the board on at least one end (both walls solid FR4 at that end — not reaching the board's
> true outline), entirely underneath a surface-mount component's own body silhouette but clear of any
> solder pad or lead: is the governing creepage path from a pad on one side of the slot to a pad on the
> other (a) the straight-line distance ignoring the slot (the slot does not count because the standard
> considers the path to run under/through the component regardless of the cutout); (b) a path that
> detours around the slot's nearest closed end and stays on the accessible top surface; or (c)
> something else — for example, is the slot disregarded because the moulded package body itself, not
> just the missing PCB material, is what defines the creepage surface? Please cite the specific
> clause/worked example (IEC 60664-1 clause 4.2 in the 2002-era text / clause 6.8 in the current
> 3.0:2020 and 3.1:2025 editions, or IEC 60335-1 Annex L, whose content beyond its table of contents was
> not accessible to this project) that the answer relies on — none of clause 4.2/6.8's 11 worked
> examples, in either edition, appears to picture this exact geometry (see §1.3).
>
> **Secondary question, only if (b) or (c) above credits the slot at all.** Does an edge-reaching
> redesign — the *same* slot with one end extended to the board's true physical outline, leaving the
> *other* end still closed — change the answer for that remaining closed end? This project's own
> geometric and topological analysis (§1.4) concludes it cannot: past a true board edge there is no FR4
> on any layer, so no creepage path can exist there at all, and the governing (shortest) pair is
> necessarily forced onto whichever end remains closed. A single connected slot cannot reach the true
> edge at *both* ends without disconnecting a region of the board (Jordan curve argument, §1.4.3) — so a
> "fully open, no closed end at all" design is not geometrically available for a mid-board component on
> this board's simple-rectangle outline. Please confirm or correct this reasoning.

### 1.3 What has been determined in-house, and how

- **The repo's own contrary claim was traced to its origin and found unsupported.**
  `scripts/measure_cross_domain_creepage.py`'s docstring states "a surface creepage path that runs
  under a component's own moulded body cannot be lengthened by a routed slot." Git history
  (`git log -p --all`) shows this sentence present, verbatim, unmodified, and **uncited**, since the
  script's first commit (`8302756d3`, 2026-07-29) — no clause reference, no evidence-document link,
  unlike every other non-trivial claim in the same docstring. It also contradicts this repo's own
  one-day-older determination for the identical part class
  (`docs/evidence/2026-07-28-conformal-coating-pd1.md`, on `main`, discussing the same UCC21550
  driver): "a slot is a board feature and reaches under the body; a coating is a surface film and does
  not." The tool's own docstring characterizes its `body_crossing` verdict as a deliberately
  conservative screening bound ("the unsafe direction here is under-reporting a body's extent... not
  over-reporting it... a conservative error"), not a compliance determination — so treating its verdict
  as closing this question would be using the tool for a purpose it explicitly disclaims.
- **Both available editions of IEC 60664-1 were checked directly for a matching worked example, and
  neither has one.** The 2002-era text (clause 4.2, IS 15382 (Part 1):2003) and the current edition
  (clause 6.8, renumbered in 3.0:2020, unchanged in content into the 3.1:2025 consolidated reissue,
  confirmed via direct TOC/figure-list comparison) both carry the identical set of 11 worked
  groove/rib/joint examples. Every one is a 2D cross-section of a feature implicitly infinite in the
  third dimension (a groove, rib, or joint running the full width of whatever is being sectioned).
  **None has a rounded or squared *end* that a creepage path would need to detour around.** A PCB slot
  milled under an SMD component — with two real, board-surrounded ends — is not what any of the 11
  examples pictures.
- **A physically-reasoned (not standards-cited) derivation** concludes the governing path detours
  around the slot's nearest closed end: creepage is a *surface* distance, and a full-depth slot removes
  the surface entirely within its own footprint, so no path can run "through" it; between the two
  remaining candidates — down one wall, along the underside void, and up the far wall, versus around the
  nearest end while never leaving the continuous top surface — the around-the-end path is never longer.
  This is consistent with, not a departure from, the standard's own stated "most unfavorable position"
  (i.e., shortest available path) principle applied to worked examples' general rule — but it is
  explicitly **not validated by any specific worked example**, and this project does not conflate the
  two.
- **Geometric achievability was verified against the real, committed board**, not assumed: courtyard
  and existing-track extraction for all 168 footprints (`kiutils`, read-only), corridor-blocking search
  for candidate slot/arm geometry, confirming clear paths to the board edge exist for T1 (17.96mm, south
  end) and U6 (60.51mm, north end, contingent on staying ≥2.0mm clear of T1's own independent slot).
  Neither reroute set (T1: 16 segments/7 nets total; U6: 19 segments/11 nets total) was checked for
  geometric legality — flagged as unverified, not executed.
- **Computational verification, not just argument, that opening one end does not change the governing
  number.** A `shapely`+`networkx` visibility-graph shortest-path search first reproduced two prior
  documents' own published baseline figures to 4 decimal places (island T1 at 28.0×8.0mm: 15.5323mm
  vs. expected 15.532mm; minimized island T1 at 28.0×4.0mm: 13.2655mm vs. expected 13.265mm), then was
  extended to the edge-reaching geometry: **13.2655mm nominal / 12.8296mm worst-case (±0.2mm/edge
  pessimistic fab tolerance) — numerically identical to the pure island design to 4 decimal places.**
  A diagnostic pair check confirms the mechanism directly: the pad pair nearest the now-open end is
  forced onto a 40.91mm detour around the still-closed end once the open end offers no path at all;
  the pair nearest the unchanged closed end remains the 13.2655mm minimum, exactly as in the island
  design. Opening one end changes *which* pair governs, not *what number* governs.
- **A topological (Jordan curve) constraint, stated for the first time this session.** The board
  outline is a single simple rectangle (`pcb/temper.kicad_pcb`'s only `Edge.Cuts` polygon, confirmed
  directly — no pre-existing internal slot or cutout anywhere). Any single connected cut whose two ends
  land at two distinct points on that outline necessarily separates the enclosed region into two
  mechanically disconnected pieces — an elementary consequence of the Jordan curve theorem for a simple
  arc with both endpoints on the boundary of a simply-connected planar region. A design touching the
  true edge at only one point per connected slot (T1's and U6's edge-reaching designs, both above) does
  not disconnect anything; touching it at two points for the same connected void does, unconditionally.
  This is also why the 2.0mm coordination clearance between T1's and U6's independent slot geometries
  (§1.5) is load-bearing, not incidental margin: if the two slots ever merged into one connected void,
  that void would touch the true edge at two points (once via each part's own arm) and disconnect the
  board region between them.

### 1.4 Geometry and figures, T1/T2/U6 (all island- and edge-reaching-slot designs)

| Part | Design | Dimensions | Removed area | Nominal creepage | Worst-case creepage (±0.2mm/edge) | Verdict vs. 12.6mm PD3 | Source |
|---|---|---|---:|---:|---:|---|---|
| T1 | Intrinsic, no slot | — | — | — | — | 9.100mm, **FAIL −3.500mm** | PR #1152 |
| T1 | Minimized island | 28.0 × 4.0mm | 112mm² | 13.2655mm | 12.8296mm | **PASS +0.230mm (1.8%)** | PR #1160 |
| T1 | Edge-reaching (south arm) | +17.96mm arm to true left edge (x=20), +3 segments/3 nets | +71.84mm² (1 layer) | 13.2655mm | 12.8296mm | **PASS +0.230mm** — numerically identical to island | This session |
| T2 | Same footprint as T1, if placed | — | — | — | — | Same as T1's, **contingent on placement** (§1.5) | PR #1152/#1155 |
| U6* | Intrinsic, no slot | — | — | — | — | 8.100mm, **FAIL −4.500mm** | PR #1152 |
| U6* | Un-minimized island | 7.30 × 17.00mm | 124.1mm² | 14.85mm | 14.11mm | **PASS +1.51mm (12%)** | PR #1155 |
| U6* | Edge-reaching (north arm) | +60.51mm arm to true left edge, MUST stay ≥2.0mm clear of T1's slot, +15 segments/9 nets | +242.04mm² (1 layer) | 14.85mm (carried forward, not independently re-derived) | 14.11mm (same caveat) | **PASS (unverified numerically for this specific geometry)** | This session |

*\*`U6` per the branch naming in §0 — this is `U7` on `main`.*

### 1.5 What is NOT established, stated explicitly

- **No certification-lab confirmation of the closed end's creepage credit, for either T1 or U6.** This
  is precisely §1.2's open question — everything above this line is in-house analysis, not a standards
  determination.
- **No FEA, mechanical, or thermal-cycling qualification exists anywhere in this repository** — checked
  exhaustively (`docs/`/`scripts/` search). T1's slot leaves the part's entire mechanical retention on
  4 solder joints around a 112mm² cutout; whether that survives reflow/field thermal cycling is an open,
  unassessed question distinct from the creepage question. U6's edge-reaching arm (60.51mm, a long
  interior slit close to T1's own slot) raises a new, equally unassessed board-flatness/warpage
  question during the reflow oven pass.
- **T2 is not placed on the committed board today** (parked 46mm past the board's own bottom edge, an
  unrelated placement infeasibility from a separate finding, not resolved by this package). Its
  creepage figures are stated as "if placed, transfers directly" — not evaluable until that separate
  problem is solved.
- **U6's edge-reaching geometry was not independently re-derived by the visibility-graph computation**
  — only T1's was. The governing-path argument is extended to U6 analytically, not numerically
  verified, and is flagged as such in §1.4's table.
- **Neither reroute set's geometric legality was checked**, and internal corner radius for the
  concave joint where an arm meets a main slot body has no published minimum from any fab checked
  (reasoned to be non-blocking — a rounded interior corner only removes more material, never less — but
  not a sourced figure).

### 1.6 Evidence to hand the certification lab with this question

1. §1.3-1.4 of this document (geometry, dimensions, worst-case fab-tolerance model).
2. Component mechanical drawings: Coilcraft CST3015 official Recommended Land Pattern (Document
   1608-2, rev 09/08/25) for T1/T2; TI UCC21550BDWKR datasheet SLUSE89C, Figure 4-2 (DWK pin
   configuration) and Figure 34 (recommended layout) for U6.
3. Either a physical sample or an accurate 3D render of the slot fully milled with the part unmounted,
   so the lab can see directly that no floor exists under the cut — removing any ambiguity about
   whether "the moulded body defines the boundary" is even a live reading.
4. The board-state disambiguation in §0 (branch, sha256, and the U6/U7 naming note) so the lab is
   working from the same geometry this package describes.

---

## 2. Question B — does IEC 60664-4 (high-frequency insulation coordination) apply at this converter's 44-50kHz tank frequency, and if so, what does it require?

### 2.1 Why this question, and why it is urgent rather than theoretical

This is a series-resonant half-bridge induction-cooktop converter. Its tank runs **44,000-50,000 Hz**
(`firmware/components/control/pll_control.h:104-105` — `PLL_MIN_FREQ_HZ 44000` / `PLL_MAX_FREQ_HZ
50000`; `elec/src/main.ato:269-273` — `f_pll_tracking_min: frequency = 44kHz` / `f_pll_tracking_max:
frequency = 50kHz`). IEC 60664-4, *Insulation coordination for equipment within low-voltage systems —
Part 4: Consideration of high-frequency voltage stress*, governs insulation coordination for periodic
voltages **above 30kHz** per its own scope — this design's entire legal operating range sits above
that threshold. The threshold is quoted from the standard's scope as published, without purchase, in
IEC's own catalogue entry for IEC 60664-4:2005 (Ed. 2.0 — the current edition;
`webstore.iec.ch/en/publication/2804`) and in the free preview PDF
(`en-standard.eu/publicdoc/iec_previews/67465.pdf`): *"applicable for the dimensioning of clearances,
creepage distances and solid insulation stressed by any type of periodic voltages with a fundamental
frequency above 30 kHz and up to 10 MHz."* This is the only part of the standard readable without
purchase; the normative dimensioning clauses are not obtainable (§2.5).

**The fact that makes this urgent, not theoretical:** IEC 60335-1 Annex J, clause 6.8.6 (CITED-PRIMARY,
quoted verbatim from IS 302-1:2008, `docs/evidence/2026-07-28-conformal-coating-pd1.md:143-146`, on
`main`):

> "6.8.6 Partial Discharge Extinction Voltage — Type A coatings are not subjected to a partial
> discharge test.
> NOTE — Partial discharges do not normally occur at voltages lower than 700 V peak."

This board's governing high-frequency node measures **923.7V peak** (§2.3) — **above** that 700V
threshold the standard itself flags as worth a note. That note is written in the context of coating
qualification, not bare-board air-gap PD in general, so it does not by itself answer whether PD testing
is warranted here — but it establishes that this design sits in a voltage range the standard considers
PD-relevant, at a frequency (44-50kHz) an order of magnitude above the mains frequency every power-
frequency clearance/creepage table in this project's toolkit was written for.

### 2.2 In-scope nets and geometry, with real numbers

All figures below: `docs/evidence/2026-08-12-hv-clearance-adequacy.md` (`main`, PR #1080), measured
live with `ngspice-42` (KLU) against `simulation/harness/nets/zvs_margin_sweep.cir` (the repo's own
committed ZVS harness, given 6 added `.meas` cards — deck topology, models, and `.options` untouched),
across the full legal 44-50kHz PLL range, cast-iron/stainless pan (worst-coupled preset), all three
L/C tolerance corners at the declared ±10% part tolerance, screened against OCP-01's measured 50.1A
peak trip (45-55A window, `docs/STRATEGY.md` §OCP-01 / `FUNCTIONAL_TEST_CRITERIA.md` §2.1). Circuit
topology, not netclass label: `SW_NODE ── [c_tank1‖c_tank2‖c_tank3] ── tank.c_tank1-p2 ── [88µH coil] ──
tank-out ── [CT primary] ── PWR_RTN`, a series-resonant half-bridge across a split ±170V bus, driven
above resonance.

| Pair | 47kHz declared nominal | 44kHz PLL floor | Worst OCP-passing point | rms (at worst-OCP point) |
|---|---:|---:|---:|---:|
| **`tank.c_tank1-p2` ↔ `DC_BUS_RTN`** (governing pair) | 699.9 V pk | 837.7 V pk | **923.7 V pk** | **570.5 V rms** |
| `tank.c_tank1-p2` ↔ `+170V_BUS` | 699.5 V pk | 837.2 V pk | 923.1 V pk | — |
| `tank.c_tank1-p2` ↔ `PWR_RTN` | 529.9 V pk | 667.7 V pk | 753.7 V pk | 544.6 V rms |
| `tank.c_tank1-p2` ↔ `SW_NODE` (across the tank caps) | 360.0 V pk | 497.8 V pk | 583.9 V pk | 411.5 V rms |
| `SW_NODE` ↔ either bus rail | 343.4 V pk | 344.4 V pk | 344.2 V pk | 240.2 V rms |
| `+170V_BUS` ↔ `DC_BUS_RTN` (full bus) | 340 V DC | 340 V DC | 400 V (declared `v_bus_abs_max`) | — |

Worst OCP-passing point occurs at L −10%, C −10% (both within declared part tolerance), 48kHz. `GATE_HS`
/ `hb.power_loop.q_high-g` (Q_high's gate, one resistor from `GATE_HS`) floats on `SW_NODE` and is
bounded by the `SW_NODE` row above.

**Out of scope, explicitly:** mains-side nets (`AC_L`, `AC_N`, `PE`, and everything upstream of the
bridge rectifier) carry 50/60Hz power-frequency voltage only — never driven by the 44-50kHz tank — and
are not part of this question.

### 2.3 What has been determined in-house — clearance

IEC 60335-1 clause 29.1.5 (CITED-PRIMARY, `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`
on `main`) is the clause explicitly naming "if there is a resonant voltage":

> "For appliances having higher working voltages than rated voltage... or if there is a resonant
> voltage, the voltage used for determining clearances from Table 16 shall be the sum of the rated
> impulse voltage and the difference between the peak value of the working voltage and the peak value
> of the rated voltage."

Applied to the worst OCP-passing peak (923.7V) at this board's OVC II / 120V-rated-voltage inputs
(1500V rated impulse per Table 15 row ii, corrected per this session's companion spec fix — see
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2):

```
V_det = 1500 + (923.7 - 169.7) = 2254V
Table 16 -> 1.5mm basic (2500V step) + 0.5mm clause-29.1 soldered-construction adder = 2.0mm required
Committed value: 2.0mm.  REQUIRED = PROVIDED, exactly, on the conservative (non-interpolated) reading.
```

**This is the pair with the least existing margin on the board.** The Table 16 step itself moves at
1169.7V peak working voltage (solved from V_det=2500). One real, in-tolerance parameter corner — L
−10%, C −10%, commanding the 44kHz PLL floor — reaches **1289.4V peak**, which *would* cross the step
and require 3.5mm. That corner is prevented only because it also draws **68.7A peak, 1.37× OCP-01's
50.1A trip threshold** — the converter trips before reaching that operating point. **The 2.0mm
clearance margin is held by OCP-01's trip threshold and the firmware's 44kHz PLL floor, not by copper
geometry.** If OCP-01's trip threshold is ever raised, or its detection delayed, this margin weakens
directly and by the same mechanism.

### 2.4 What has been determined in-house — creepage

IEC 60335-1 Table 17 (CITED-PRIMARY, cross-checked cell-for-cell against an independent reproduction),
material group IIIa/IIIb, row vi (>500-≤800V): **6.3mm PD2 / 10.0mm PD3 basic**. At 570.5Vrms, the
governing tank↔rail pair lands in this row.

**Nothing in this repository enforces a creepage constraint for this pair at all.** Verified two ways:
(1) rule inventory — `scripts/generate_kicad_dru.py` emits `creepage` constraints in exactly three
rules, all requiring one side to be non-HighVoltage; the only HighVoltage-internal rule is
clearance-only and additionally conditioned on both pads sharing the same component reference; (2)
empirically — raising the `HighVoltage` netclass clearance to 20mm on a scratch copy of the board moved
the clearance violation count (386→499) but not the creepage count (183-184 unchanged), confirming no
creepage rule fires for this pair at any clearance setting.

Provided: 2.0mm (the flat, ungrooved, uncoated surface — same physical distance as the clearance figure
since there is no slot between these pads and `COATING_QUALIFIED = False`). **This is a 3.2× (PD2) to
5.0× (PD3) shortfall on a distance nothing currently checks.**

**Clause 29.2.4's functional-insulation exemption does not rescue this pair.** This boundary is
functional insulation (both sides hazardous-live, no shock barrier crossed). Clause 29.2.4 (CITED-
PRIMARY, `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`, `main`) reads: "Creepage distances
of functional insulation shall be not less than those specified in Table 18. However, creepage
distances may be reduced if the appliance complies with 19 with the functional insulation
short-circuited." Table 18 (Minimum Creepage for Functional Insulation) is **numerically identical to
Table 17 from >500V upward**, verified cell-by-cell — at 570.5Vrms the reclassification changes the
citation, not the figure (still 6.3mm PD2 / 10.0mm PD3). The exemption's condition — passing clause
19's abnormal-operation test with the gap short-circuited, physically a dead short from the tank node
to a bus rail across a running 1.8kW resonant converter — **has not been performed, simulated, or
analyzed anywhere in this repository.**

### 2.5 The IEC 60664-4 gap itself

The string "60664-4" appears in four documents now on `main` — all of which *raise* the applicability
question and none of which *resolves* it: `docs/evidence/2026-08-12-hv-clearance-adequacy.md` §3.3
("What I could not close: IEC 60664-4") is the earliest and most explicit — it notes the 44-50kHz tank
sits above the standard's own >30kHz scope and lists the sub-questions §2.6 below formalizes for the
lab; `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` §6, `docs/evidence/2026-08-12-pollution-degree-resolution.md`
§7, and `docs/evidence/2026-08-12-unassigned-domain-nets.md` §1.2 record the same open item. (An
earlier in-repo search recorded the string as appearing zero times —
`docs/evidence/2026-08-12-hv-clearance-adequacy.md:345` — as of 2026-08-12, before that document
itself merged via PR #1080; a later writer repeated the claim without re-searching.) **No document
anywhere has resolved whether this converter's switching frequency invokes the standard, and none
contains any of IEC 60664-4's normative dimensioning figures** — that is the gap this question sends
to the lab.

**IEC 60664-4's own normative tables are not obtainable by this project.** What *is* publicly readable
without purchase is the standard's scope paragraph, quoted in §2.1 from IEC's own catalogue entry
(`webstore.iec.ch/en/publication/2804`) and the free preview PDF
(`en-standard.eu/publicdoc/iec_previews/67465.pdf`, which reproduces the scope and foreword in full):
those confirm the ">30kHz" applicability threshold but contain no dimensioning values. The normative
clauses (4/5/6 — high-frequency clearance, creepage, and solid-insulation dimensioning) and the
annexes that would let anyone compute the actual factors remain paywalled; unlike IEC 60335-1
(recovered via IS 302-1:2008, an identical Bureau of Indian Standards adoption published under India's
RTI Act), IEC 60664-4 has no equivalent national-adoption or full-text public-archive route found.
This session's task brief states its tables were confirmed paywalled at every vendor checked — **that
specific vendor-by-vendor search is not itself recorded in a committed evidence document this package
can cite by exact location**, so it is reported here as this session's own finding rather than a
re-verifiable prior determination, and flagged as such rather than smoothed over. **No figure from IEC
60664-4's normative tables is used, invented, or estimated anywhere in this document.**

**Review corrections, 2026-08-15** (this section rewritten during finalization): the draft's claim that
the string "60664-4" had "zero occurrences" in this repository, and that "no document anywhere has
considered whether this converter's switching frequency invokes it," was accurate as of 2026-08-12
(when `docs/evidence/2026-08-12-hv-clearance-adequacy.md` §3.3 recorded the same search result) but
false by the time this package was assembled — PRs #1080/#1081 had since merged that document and
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` to `main`, both of which raise exactly this
question at 44-50kHz. The four documents on `main` named above are the question's true origin; this
package's §2.6 is the first to formalize it for a lab. The draft's paywall claim was also sharpened:
the standard's scope paragraph is publicly readable (IEC catalogue entry + free preview PDF, cited in
§2.1), and only the normative dimensioning clauses are unobtainable. No figure was changed by these
corrections.

### 2.6 The precise questions to ask the lab

> 1. Does IEC 60664-4 apply to a PCB-internal functional-insulation clearance/creepage boundary
>    carrying a periodic (not sinusoidal mains-frequency) voltage whose fundamental frequency is
>    44,000-50,000 Hz? If so, what frequency-dependent factor applies to (a) the clearance figure
>    derived above (IEC 60335-1 clause 29.1.5 / Table 16, 2.0mm required at 923.7V peak determining
>    voltage 2254V) and (b) the creepage figure derived above (Table 17/18 row vi, 6.3mm PD2 / 10.0mm
>    PD3 at 570.5Vrms)? Please cite the specific clause/table.
> 2. Is partial-discharge inception testing warranted for a recurring peak voltage of 923.7V across a
>    ~2.0mm air gap at 44-50kHz, given IEC 60335-1 Annex J's own 700V-peak note (§2.1)? That note is
>    written for coating qualification, not bare-board air-gap PD — does the same 700V threshold, or a
>    different frequency-adjusted one, apply to an uncoated gap at this frequency?
> 3. Does IEC 60664-4 (or IEC 60335-1's own text) impose anything beyond what clause 29.1.5's
>    determining-voltage arithmetic already computes for a resonant/higher-than-rated working voltage
>    (Table 15 Note 2, CITED-PRIMARY: "the values are based on the assumption that the appliance will
>    not generate higher overvoltages than those specified. If higher overvoltages are generated, the
>    clearances have to be increased accordingly")? Our own reading is that clause 29.1.5 is the
>    mechanism Note 2 points at — the standard does not say so explicitly, and we would like that
>    confirmed or corrected.
> 4. **Asked, not answered, here.** The only isolation-barrier component remaining in this design with
>    a galvanic barrier crossing is the UCC21550 gate driver (`U6`/`U7` per §0's naming note; the
>    ADUM1250 I2C isolator this project's own spec once referenced — `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
>    §6.3 — was removed from the design entirely: `elec/src/components.ato:51-54`, "isolation is
>    provided by the AuxSupply transformer... not an I2C isolator," confirmed absent from
>    `pcb/temper.kicad_pcb` and `docs/hardware/BOM.md:238`). Note that the spec's own §6.3 bullet and
>    §8.1 verification-checklist row still list the removed part — stale artifacts, marked superseded
>    in that document on 2026-08-15 and to be read as such; the design's live position is
>    `elec/src/components.ato:51-54` / `docs/hardware/BOM.md:238`. The gate driver's secondary side floats on
>    `SW_NODE`, which switches at 44-50kHz. Does the barrier's own pad-gap creepage/clearance rating
>    (datasheet-specified against DC/mains-frequency withstand) need re-examination for the same
>    high-frequency periodic stress question raised above, or is a galvanically isolated barrier's
>    stress profile categorically different from the same-domain functional-insulation gap this package
>    otherwise asks about?

### 2.7 Exposure if the answer is more demanding

This pair already carries the two largest risk factors on the board simultaneously: **it is the pair
with the least existing clearance margin** (2.0mm required / 2.0mm provided, an exact Table 16
step-boundary coincidence rather than a design margin — see §2.3), and **its margin is held by a
protection function (OCP-01's trip threshold), not by geometry.** If IEC 60664-4 requires any
frequency-derating factor greater than 1.0× on top of the power-frequency Table 16 figure, this exact
pair moves from "exactly adequate" to "inadequate," with zero present margin to absorb it — a wholesale
`HighVoltage` netclass clearance increase is not free either: measured directly, raising the class from
2.0mm to even 3.0mm costs +5 new clearance violations and breaches both the DRC category and aggregate
error ceilings (`docs/evidence/2026-08-12-hv-clearance-adequacy.md` §5), so any required increase would
need a scoped fix (e.g., a separate `HighVoltageTank` netclass carrying only `tank.c_tank1-p2`, measured
to cost zero additional violations up to 4.0mm), not a blanket rule change.

Creepage is already a known, unenforced 3.2-5.0× shortfall at power-frequency figures alone (§2.4), with
no gate anywhere in this repository checking it. Any additional high-frequency consideration from
IEC 60664-4 only adds to a deficit that already exists today, independent of this question's answer.

If Q4 above returns "yes, re-examine the barrier": the UCC21550's own reinforced-isolation rating
(5700V RMS, per the isolation barrier's existing hi-pot test requirement,
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §8.3) is a DC/AC-mains-frequency withstand figure; whether
it also covers 44-50kHz periodic stress across the same barrier has not been checked anywhere in this
project and would be a new, separate finding this package does not attempt to resolve.

### 2.8 Evidence to hand the certification lab with this question

1. §2.2-2.6 of this document (nets, figures, derivations, both questions verbatim).
2. `simulation/harness/nets/zvs_margin_sweep.cir` (the committed simulation deck the peak/rms figures
   were measured from) and a description of the 6 added `.meas` cards, available on request.
3. `docs/evidence/2026-08-12-hv-clearance-adequacy.md` and `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`
   in full (both on `main`) for the complete derivation chain and every caveat this summary compresses.
4. UCC21550BDWKR datasheet (SLUSE89C) for the barrier's own datasheet isolation rating, if Q4 is
   pursued.

---

## 3. Summary — measured, computed, and could-not-be-sourced

**Measured** (live, against real artifacts, this project's own instrumentation):
- T1/T2/U6 intrinsic (unslotted) creepage: 9.100mm / 8.100mm — rotation-and-side-aware pad-geometry
  kernel against the real committed board (Question A, unmerged branches per §0).
- Island- and edge-reaching-slot creepage for T1 (both designs): 13.2655mm nominal / 12.8296mm
  worst-case — visibility-graph shortest-path computation, verified by reproducing prior published
  figures to 4 decimal places before extending (Question A).
- Tank-node peak/rms voltages across all `HighVoltage` pairs, full 44-50kHz legal envelope, all L/C
  tolerance corners: 923.7V peak / 570.5Vrms governing figure — live `ngspice-42` simulation against
  the committed ZVS harness (Question B, `main`).
- OCP-01 trip threshold: 50.1A peak, against a 45-55A requirement window (Question B, `main`).
- DRC blast-radius of various `HighVoltage` clearance settings (386→499 violations at 2.0mm→20.0mm):
  live `kicad-cli 10.0.5` runs against scratch copies of the real board (Question B, `main`).

**Computed / derived from CITED-PRIMARY standards text** (no value invented, interpolated, or
estimated beyond what the standard's own tables/clauses give directly):
- Required clearance at 923.7V peak (2.0mm, IEC 60335-1 clause 29.1.5 + Table 16 + clause 29.1 adder).
- Required creepage at 570.5Vrms (6.3mm PD2 / 10.0mm PD3, Table 17 row vi = Table 18 row vi).
- Required creepage for T1/T2/U6's HV↔SELV boundary at PD3 (12.6mm, Table 17 row iv).
- The Table 16 step boundary itself (1169.7V peak) and the OCP-01/PLL-floor margin analysis around it.

**Could not be sourced — the entire reason this package exists:**
- Whether a bounded/island (or edge-reaching-but-one-end-closed) PCB slot earns creepage credit at its
  closed end. No edition of IEC 60664-1 checked (2002-era or current 3.0:2020/3.1:2025) pictures this
  geometry among its 11 worked examples. IEC 60335-1 Annex L was named as a possible source but its
  content beyond the table of contents was not accessible to this project.
- Whether IEC 60664-4 applies to this board's 44-50kHz functional-insulation gaps, and if so, what
  frequency-dependent factor it imposes. IEC 60664-4's normative tables were not obtainable by any
  route this project could find or verify.
- Whether partial-discharge inception testing is warranted at 923.7V peak / 44-50kHz across a 2.0mm
  gap. The only PD-adjacent primary text found anywhere (Annex J's 700V-peak note) is written for
  coating qualification, not this scenario, and does not settle it either way.

---

## 4. Files

- This document: `docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md`.
- Companion, same session: `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` (OVC III→II and AC-Mains
  120-240V→120V corrections — documentation-only, no enforced value changed) and
  `docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md` (same OVC correction).
- Companion, review pass 2026-08-15: `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.3/§8.1 stale
  ADUM1250 rows marked superseded (documentation-only — the part was removed from the design on
  2026-07-30, see §2.6 Q4).
- Question A sources (all on unmerged branches, see §0 table): PR #1152 (`analysis/hv-creepage-pd3-gap`),
  PR #1155 (`analysis/slot-creepage-rescue`), PR #1160 (`analysis/creepage-island-t1-structural`), and
  this session's edge-reaching-slot document (`analysis/edge-slot-through-cut-rescue`).
- Question B sources (all on `main`): `docs/evidence/2026-08-12-hv-clearance-adequacy.md`,
  `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`, `docs/evidence/2026-07-28-conformal-coating-pd1.md`,
  `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`, `docs/evidence/2026-08-11-pd2-decision-record.md`,
  `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`.
- Not modified by this document: `pcb/temper.kicad_pcb`, any footprint, any DRU threshold, any
  enforced safety constant, `scripts/generate_kicad_dru.py`, `scripts/check_creepage_clearance_drift.py`,
  `temper-drc-rs/src/rules/safety/creepage.rs`, `temper-orchestration/src/clearance.rs`.
