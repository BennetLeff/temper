<!-- provenance: commit=adf482564470c02cdf849c52be48db3ec0d5365a dirty=false -->

# Isolation-barrier geometry: what would actually work on `pcb/temper.kicad_pcb`

**Date:** 2026-08-08
**Branch:** `analysis/isolation-barrier-geometry` (worktree branched from
`spike/selv-hv-pour-barrier-drc` @ `adf48256`, per this task's own constraint)
**Scope:** analysis only. No change to `pcb/temper.kicad_pcb`,
`power_pcb_dataset/drc_ceiling.json`, `elec/`, or `docs/wave4-verdicts.yaml`.
**Companion artifact:** `docs/evidence/2026-08-08-isolation-barrier-candidate-geometry.json`

---

## Executive verdict

**No isolation-barrier geometry -- straight line, piecewise-linear polyline,
or single general polygon region -- can achieve the required 8.0mm
IEC 60335-1 REINFORCED creepage separation between this board's HV and SELV
domains at its current component placement.** This is proven, not merely
searched-and-not-found: a bichromatic Delaunay cycle in the combined
HV+SELV pad-center point set (Sec. 4) is a topological obstruction that
rules out *every* simple (non-self-intersecting) curve, of any shape or
complexity, not just the straight lines and polylines this analysis also
tested directly. A convex-hull mutual-containment result (Sec. 4) separately
rules out any single closed-loop (polygon) barrier. The only geometry class
the task asked about that isn't ruled out by these two proofs -- "multiple
disjoint barriers" -- is addressed in Sec. 6: it is not ruled out in
principle, but the measured scale of interleaving (Sec. 5) means the
disjoint-region count needed is on the order of "one per interleaved
component," which is not a barrier in any electrically meaningful sense.

This independently reproduces, via a different (project-blessed,
rotation-bug-corrected) code path, the same conclusion already reached
twice on this project: `origin/safety/mains-selv-isolation-barrier`
(commit `645154b7`, kiutils-based) and `docs/evidence/2026-08-03_mains_selv_barrier_falsification.py`
(also kiutils-based, via `check_isolation_keepout.py`). Three independent
measurements agreeing is strong evidence this is a real placement property
of the board, not a tooling artifact.

**What this means for the blocked safety decision:** the DRC detector built
on `spike/selv-hv-pour-barrier-drc` is not blocked on a missing schema
feature or a missing config key alone -- it is blocked on there being no
placement on which *any* barrier geometry, however complex, would be
honest to certify. Wiring a barrier into `temper_constraints.yaml` today,
in any shape the current or a moderately-extended schema supports, would
either certify a barrier that provably does not separate the domains, or
require carving so many individual per-component exemptions that the
"barrier" stops meaning anything. **Placement remediation must happen
before a barrier can be defined**, not after.

---

## 0. Methodology

All figures below come from a Python script
(`/tmp/.../scratchpad/isolation_barrier_analysis.py`, reproduced inline
where relevant) run against this worktree, using only project-blessed
parsing code:

- `temper_placer.io.kicad_parser.parse_kicad_pcb` -- the project's PCB
  parser (Rust-backed, `temper_design_bundle_python.parse_engine`).
- `temper_placer.core.pin_geometry.pin_world_position` -- the project's
  **canonical** rotation-and-side-aware pad-world-position function (see
  "Parser bug found" below for why this, and not the parser's raw
  `ParseResult.pads` field, is what this analysis uses).
- `temper_placer.core.pad_geometry.pad_bounding_radius` / `pad_pair_distance`
  -- the project's exact, shape-aware pad geometry.
- `temper_placer.io.real_board._load_manifest` -- the project's own
  `elec/domain_manifest.yaml` reader (fails closed on a net declared in
  both domains; none found).

No hand-rolled `.kicad_pcb` text parsing was used anywhere in this
analysis. Environment note: the worktree's own `.venv` was not pre-built
(no compiled `temper_design_bundle_python`); the analysis ran with
`PYTHONPATH` pointed at this worktree's Python source (the branch under
analysis) against the main checkout's already-built native extension. The
native parse-engine crate is unchanged between the two checkouts for this
task's purposes (only `temper-drc-rs` differs on the spike branch), and
this is stated here for provenance rather than treated as a caveat on the
numeric results, which come entirely from parsing the real
`pcb/temper.kicad_pcb` file present in the analysis worktree.

**Parser bug found (reported, not fixed -- out of this task's scope):**
`ParseResult.pads` (`extract_pads_pure` in
`packages/temper-design-bundle/src/parse_engine.rs`) computes a pad's world
position as `footprint_position + pad_local_offset`, with **no rotation
applied at all** -- confirmed by comparing it against
`pin_world_position()` (which does apply the project's own sanctioned
`rotate_local_to_world_deg` -- see
`temper_placer/geometry/kicad_transform.py`'s module docstring, which
documents this exact R(-theta) convention as independently confirmed
against real `kicad-cli` DRC output) for every pad on the real board: **444
of 527 pads (84%) disagree by more than 0.01mm**, e.g. `C1` pad 2: naive
`(66.49, 214.22)` vs. correct `(51.49, 199.22)` -- a 21mm error. This
analysis therefore uses `pin_world_position(pin, comp)` throughout, never
`ParseResult.pads`. All footprint rotations on this board are confirmed
multiples of 90 degrees (`grep`'d from the raw file), so
`Component.initial_rotation` (quantized to 0/90/180/270) loses no
precision here and `pin_world_position` is exact, not merely
approximately-rotation-aware, for this specific board.

---

## 1. The HV and SELV point sets

`elec/domain_manifest.yaml` declares 21 HV nets and 33 SELV nets. Matching
every pad's `net` field (from the real board) against these declarations
gives:

| Domain | Pads | X range (mm) | Y range (mm) | Centroid |
|---|---|---|---|---|
| HV | 103 | 21.240 - 168.000 | 21.500 - 246.597 | (83.321, 139.582) |
| SELV | 221 | 21.240 - 171.000 | 21.205 - 252.675 | (94.037, 119.888) |

Board (`Edge.Cuts`, re-derived from `result.board`, not assumed):
152mm x 234mm, origin (20, 20), i.e. outline (20,20)-(172,254) -- matches
every prior evidence doc's figure.

The two domains' bounding boxes are **almost identical** (HV and SELV both
span nearly the full board in both axes) -- this alone is a strong sign no
single-axis split will work well, confirmed quantitatively below.

324 of the board's 527 pads matched a declared net. 85 distinct net names
present on real pads are not in the manifest at all (e.g. `I_SENSE`,
`OVP_VREF_2V5`, several `discharge.*` sub-nets) -- these are unclassified,
not misclassified; they are excluded from both point sets, exactly as the
production `real_board.py` loader also treats unclassified nets (reported
as a fact, not a finding this task was scoped to resolve).

---

## 2. Confirming (not refuting) the straight-line finding

**Confirmed: no straight line separates the two domains**, independently
reproducing `645154b7`'s conclusion with fresh numbers from a different
code path.

**Exhaustive axis-aligned best split** (every candidate midpoint between
adjacent distinct pad coordinates, both axes):

- best `x` split: `x=21.245mm` -- misclassifies 106/324 pads (32.7%)
- best `y` split: `y=221.223mm` -- misclassifies 106/324 pads (32.7%)

Both "best" positions sit at the extreme edge of the board's pad
distribution -- i.e. the exhaustive search found that **no interior split
does meaningfully better than trivially assigning nearly everything to one
class**. Restricting the search to interior positions with at least 10% of
pads on each side (a fairer proxy for "an actual barrier, not a
degenerate edge case") gives `x=26.027mm`, 112/324 wrong (34.6%), and
`y=221.795mm`, 114/324 wrong (35.2%) -- no better.

At the one specific candidate line that predates this analysis
(`origin/safety/mains-selv-isolation-barrier`'s `x=94.703mm`, the
HV/SELV pad-centroid midpoint): **133/324 pads misclassified (41.0%)** in
the orientation matching that branch's own stated intent (HV right of the
line, SELV left) -- worse than the exhaustive best-fit, confirming that
line was never claimed to be optimal, only "best-supported from centroid
delta," and independently showing it is not close to viable either.

(These figures use only axis-aligned candidates; `645154b7`'s own
28-32%-of-318-pads figure came from a search over all 180 degrees of
orientation, which can only do as well or better than an axis-aligned
search. The two results are consistent -- both land in the same
"roughly a third of pads land on the wrong side no matter where the line
goes" regime.)

---

## 3. How non-separable: the decisive, curve-independent proof

A straight-line search can only ever produce "how bad is the best line" --
it cannot prove no *curved* or *polyline* boundary does better. The
decisive question the task asked is answered by a different, exact test:

**Is the combined HV+SELV pad-center point set separable by *any* simple
curve at all** (straight, curved, or piecewise, open or closed)? This is
answered by checking for a **bichromatic cycle in the Delaunay
triangulation** of the combined point set: a Delaunay edge connects two
points with an empty circumscribing disk between them (a genuine
visibility/adjacency relationship, not an artifact of triangulation
choice), so an alternating ring of HV/SELV Delaunay edges is a
topological obstruction -- no simple curve can separate the ring's
members without crossing at least one Delaunay edge, regardless of how
the curve is drawn.

**Result: FOUND. A 12-pad alternating ring:**

```
SELV  C6     pad  2   net=gnd                              (65.990, 211.760)
HV    R8     pad  2   net=PWR_RTN                           (71.250, 222.195)
SELV  K1     pad A2   net=power_in.bypass_relay-coil2       (92.055, 221.395)
HV    R8     pad  1   net=zcd                                (71.250, 223.845)
SELV  R75    pad  1   net=+3V3                               (80.475, 242.770)
HV    C27    pad  2   net=tank.c_tank1-p2                    (68.620, 242.000)
SELV  C9     pad  1   net=+15V                                (88.150, 252.675)
HV    U5     pad  3   net=SW_NODE                            (23.720, 244.150)
SELV  Q1     pad  1   net=power_in.bypass_relay-coil2         (21.250, 217.107)
HV    U5     pad  1   net=hb.power_loop.q_high-g              (23.720, 233.250)
SELV  U10    pad  2   net=gnd                                 (38.828, 220.800)
HV    R27    pad  2   net=GATE_LS                             (57.002, 223.100)
```
(then back to C6, closing the ring; strictly alternating HV/SELV.)

**This exact 12-pad list -- same components, same pads, same net names --
matches `docs/evidence/2026-08-03_mains_selv_barrier_falsification.py`'s
independently-computed cycle byte-for-byte**, despite that script using
kiutils (a different parser) for pad extraction. Two independently-coded
parsers, one of which (this analysis) uses the project's own blessed
rotation math and specifically avoids the buggy `ParseResult.pads` field
(Sec. 0), agree exactly. This is strong evidence the finding is a real
geometric property of the board, not a parsing artifact from either side.

**Loop-form barriers are also ruled out.** A convex-hull mutual-containment
check (does one domain's convex hull contain points of the other?):

- **121 of 221 SELV pads sit inside the HV convex hull** (60 distinct
  SELV component refs)
- **95 of 103 HV pads sit inside the SELV convex hull** (49 distinct HV
  component refs)

No closed loop can enclose one domain's pads without also enclosing a
majority of the other's. This rules out a single general polygon region,
not just a single straight line.

**Answering the task's geometry menu directly:**

| Candidate | Verdict | Evidence |
|---|---|---|
| Straight line | Refuted | Sec. 2: best case 32.7-41.0% pad misclassification |
| Polyline / piecewise-linear boundary | Refuted | Sec. 3 Delaunay-cycle proof rules out ANY simple open curve; Sec. 6 shows a 16-segment piecewise-vertical polyline still misclassifies 22.5% |
| General polygon region (single, closed) | Refuted | Sec. 3 convex-hull mutual-containment: 60/49 refs interleaved into the "wrong" hull |
| Multiple disjoint barriers | Not ruled out in principle, but degenerates to near-per-component exemptions | Sec. 5-6 |

---

## 4. Naming the offenders

The 12-pad cycle above touches 10 distinct components. Two are **declared
isolators** by design (legitimately dual-domain, per
`elec/domain_manifest.yaml`'s `protective_impedance_chains` /
mixed-domain component convention) -- `C6` (`power_in.y_cap_pe`, the
Y-capacitor to protective earth) and `K1` (`power_in.bypass_relay`, whose
mechanical contacts legitimately span the isolation boundary). Their
presence in the cycle is expected and not a placement defect.

The other **8 are ordinary, single-domain components with no declared
reason to sit near the opposite domain**, and are the real offenders:

| Ref | Domain | Sheetpath | Role |
|---|---|---|---|
| R8 | HV | `power_in.r_zcd_bot` | ZCD divider bottom resistor |
| R75 | SELV | `mcu.r_en` | MCU enable resistor |
| C27 | HV | `tank.c_tank3` | Resonant-tank capacitor (400V-rated) |
| C9 | SELV | `power_mgmt.buck_3v3.c_in` | 3.3V buck regulator input cap |
| U5 | HV | `hb.power_loop.q_high` | Half-bridge high-side MOSFET |
| Q1 | SELV | `power_in.q_relay_drv` | K1 relay-driver transistor |
| U10 | SELV | `rtd_pan.reference` | RTD reference IC |
| R27 | HV | `hb.gate_ls.rg_on` | Low-side gate-drive resistor |

A plausible root cause for at least one pair: `Q1` (the SELV transistor
that *drives* the `K1` relay coil) is naturally placed close to `K1`
itself, and `K1`/the HV bypass circuitry (`U5`, `R8`, `R27`) sit nearby --
a common "driver near what it drives" layout instinct that, on this board,
lands a SELV transistor inside the HV cluster.

**How bad, quantitatively, beyond this one cycle:** removing all 8 of
these components' pads and re-running the Delaunay-cycle test still finds
a bichromatic cycle in the remaining 308 pads -- the 12-pad ring is not the
only obstruction, only the smallest/first one found. A bounded greedy
stress test (repeatedly remove the highest-bichromatic-degree component
and retest, capped at 60 iterations) needed to remove **53 of the board's
~150 populated components -- effectively the entire HV domain down to 6
residual HV pads -- before the bichromatic adjacency graph became acyclic.**
This is a blunt heuristic (it does not find a true minimum, and is
structurally biased toward stripping the smaller class, HV), reported here
only to establish scale, not as "53 components must move": it shows the
interleaving is **pervasive across most of the HV domain, not a small,
fixable pocket of 8 parts**. The 8 named above remain the right, precise,
smallest concrete starting point (they are the exact, minimal, named
witnesses to non-separability) -- but placement remediation should expect
to need to look at layout more broadly than just those 8, not treat them
as a complete punch list.

---

## 5. Checked against the real requirement (8.0mm creepage)

Two separate questions: (a) does *today's placement* already violate
8.0mm HV-SELV pad clearance, independent of any barrier; (b) does a
proposed barrier achieve it.

**(a) Closest real HV-SELV pad pairs, independent of any barrier.**
Coarse-pruned to pairs within 20mm (conservative bound: center distance
minus each pad's `pad_bounding_radius`, which never over-reports
clearance), then the 10 closest were re-measured **exactly**, using each
pad's true shape and the project's canonical rotation composition
(`Component.initial_rotation * 90 + Pin.pad_rotation_deg`, verified all
components are on a single board side so no mirroring correction was
needed):

| Pair | Exact clearance | Note |
|---|---|---|
| K1 pad 13 <-> K1 pad A1 | **8.0000mm** | Isolator (relay), zero margin |
| K1 pad 14 <-> K1 pad A2 | **8.0000mm** | Isolator (relay), zero margin |
| C6 pad 1 <-> C6 pad 2 | **8.0000mm** | Isolator (Y-cap), zero margin |
| K1 pad 13 <-> K1 pad A2 | 8.5494mm | compliant |
| K1 pad 14 <-> K1 pad A1 | 8.5494mm | compliant |
| T1 pad 1 <-> T1 pad 4 | 9.1000mm | compliant |
| U7 pad 9 <-> U7 pad 8 | 8.1000mm | compliant |
| U7 pad 14 <-> U7 pad 3 | 8.1000mm | compliant |
| U6 pad 1 <-> U25 pad 8 | 9.9700mm | compliant |
| RT1 pad 2 <-> U15 pad 3 | 8.4552mm | compliant |

None of the 10 closest pairs checked is below 8.0mm; three (all on
declared isolator components, K1 and C6) sit at **exactly** 8.0000mm --
the design was evidently placed to hit this minimum precisely, not by
accident. **This is itself a load-bearing finding for barrier feasibility:
a component whose own HV pin and SELV pin are 8.000mm apart with zero
spare margin has no room for an 8mm-wide keepout corridor to physically
pass between them at all** -- any barrier corridor must route *around*
such isolator footprints, which every practical barrier design already
has to do by carving a documented exemption for declared isolators (this
is normal and expected, unlike the 8 non-isolator offenders in Sec. 4).

This pad-pair spot-check is narrower than, and should not be confused
with, `test_temper_board_clearance_compliance` (REQ-SAFE-01)'s reported
76 violations / 33 pairs -- that check covers copper (traces/zones), not
just pad centers, over a broader model; this section's 10-pair sample is
a targeted cross-check of the specific near-miss pairs this analysis's own
search surfaced, not a replacement for REQ-SAFE-01.

**(b) Copper-exclusion headroom.** Zone-polygon coverage of the board area
(computed directly from `result.board.zones`, this analysis's own fresh
measurement): **73.7%** of the 35,568mm^2 board area is already inside a
copper zone/pour polygon. This is a different (narrower -- zones only, no
trace/via/pad buffering) measurement than
`2026-08-03_mains_selv_barrier_falsification.py`'s 85.7% (which unions
zones with traces, vias, and pads), but agrees on the conclusion: **most
of the board is already copper, leaving little room for an unobstructed
8mm corridor anywhere**, independent of the domain-separability problem
above.

---

## 6. Testing the schema's own multi-barrier capability against this board

`constraints::IsolationBarrier` (`packages/temper-drc-rs/src/constraints.rs:70`)
is `{name, x_mm, y_span: [f64;2], layers, clearance_mm}` -- **one vertical
line segment**. `ConstraintSet::isolation_barriers` is already a `Vec`,
and `IsolationBarrierCheck::check()` evaluates each barrier independently
-- so **a piecewise-vertical ("stepped") polyline, where the barrier's x
position changes at different y-bands, is already expressible with zero
Rust changes**, by supplying multiple `IsolationBarrier` entries with
non-overlapping `y_span`s.

This analysis tested whether that already-supported capability would be
enough, by finding the best per-band x-split for K=1,2,4,8,16 equal-height
bands spanning the board:

| K bands | Misclassified pads | % |
|---|---|---|
| 1 (single line) | 106/324 | 32.7% |
| 2 | 106/324 | 32.7% |
| 4 | 95/324 | 29.3% |
| 8 | 83/324 | 25.6% |
| 16 | 73/324 | 22.5% |

Even 16 bands (a fairly fine-grained stepped polyline, ~14.6mm per band)
only reaches 22.5% -- diminishing returns, not convergence toward zero.
This is the practical face of the Sec. 3 topological proof: the underlying
conflict recurs at very small y-scales -- e.g. `R27` (HV, y=223.100) and
`U10` (SELV, y=220.800) require the barrier on one side of them, while
`R8` (HV, y=222.195/223.845) and `K1.A2` (SELV, y=221.395) -- all within
the same ~3mm y-band -- require the opposite ordering. A boundary that is
a function of y (any vertical-segment polyline, however finely stepped)
cannot satisfy both simultaneously; only a boundary that can also vary in
the other direction (a true 2D polygon boundary, per Sec. 3, or physically
moving one of these four parts) can.

The full 16-band candidate (concrete coordinates) is recorded in
`docs/evidence/2026-08-08-isolation-barrier-candidate-geometry.json` under
`stepped_polyline_candidate_16band`, explicitly labeled non-compliant.

---

## 7. What the detector would need -- schema extension and cost

1. **Multiple vertical-segment barriers (a stepped/piecewise-vertical
   polyline): already supported, zero Rust changes.** `Vec<IsolationBarrier>`
   plus independent per-entry evaluation is already what
   `IsolationBarrierCheck` does. Sec. 6 shows this alone would not be
   sufficient on the *current* placement, but it is free capability worth
   knowing about for a future placement where a stepped boundary suffices.
2. **A true general polyline (non-vertical segments, e.g. a diagonal jog):
   a moderate, well-scoped Rust change, not a rewrite.** Per
   `docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md` Sec. 6.4
   (this project's own prior assessment, which this analysis agrees with):
   swap `x_mm: f64, y_span: [f64;2]` for an ordered vertex list
   (`geo::LineString` already supports the needed distance/intersects
   operations uniformly with the current `Line`-based code, per that
   crate's own API). Touches: the `IsolationBarrier` struct + serde
   shape, the barrier-line construction in `isolation_barrier.rs`, and
   the 4 existing intersection/distance call sites (trace-crossing,
   zone-crossing, trace-clearance, zone-clearance), plus new unit tests
   for a polyline case. **This would NOT fix this board** -- Sec. 3's
   Delaunay-cycle proof rules out any simple open curve, polyline or not.
3. **A general polygon-region (containment-based) check: substantially
   more work, closer to a new check than an extension.** The current
   check's violation semantics are "distance/intersection to a line";
   containment ("is HV copper inside a region declared SELV, or vice
   versa") is a materially different test, would need its own violation
   codes, and was not attempted or scoped here in any implementation
   sense. Also would not fix this board per Sec. 3's convex-hull
   containment result, so building it now would be speculative work
   against an unentered future state.
4. **No config -> `IsolationBarrier` wiring exists at all today** (already
   noted in the 2026-08-08 spike doc, unchanged by this analysis):
   `temper_constraints.yaml` has no `isolation_barrier` key and nothing
   builds `ConstraintSet.isolation_barriers` from YAML. This is a
   separate, smaller gap from the geometry-model question above, and
   remains open regardless of which geometry class is eventually adopted.

**None of the above should be built before placement remediation.** Every
schema extension this section describes would have nothing valid to
express until a placement exists on which some barrier geometry actually
separates the domains -- building the polyline or polygon machinery now
would be schema work in search of a problem it cannot yet solve.

---

## 8. Recommendation

1. **Do not adopt any barrier geometry today.** Every candidate this
   analysis tested or could construct -- including the best-effort 16-band
   stepped polyline -- fails to separate the domains, several by a wide
   margin. Adopting one anyway to unblock the DRC gate would either
   silently exempt real violations or require so many carve-outs it
   stops functioning as a barrier.
2. **Placement remediation is the actual next step, not a barrier
   geometry decision.** The 8 named non-isolator offenders in Sec. 4 are
   the smallest, most precise, evidence-backed starting point (each is
   part of the exact 12-pad topological obstruction), but Sec. 4's
   stress test shows the problem is broader than those 8 alone --
   remediation should re-run this analysis's Delaunay-cycle and
   convex-hull tests after each candidate placement change, using them as
   a pass/fail oracle ("is a bichromatic cycle still present?"), rather
   than targeting a fixed component list.
3. **Once a placement passes both topological tests (no bichromatic
   cycle, no convex-hull mutual containment), re-run this exact analysis
   to derive concrete barrier coordinates against the real, fixed
   geometry** -- do not pre-guess barrier coordinates ahead of a placement
   that has not yet been shown separable, per this task's own hard
   constraint against inventing coordinates.
4. **Schema work (Sec. 7) can proceed in parallel but gates on nothing
   here being adopted** -- the multi-barrier (stepped-vertical) capability
   is free today; the polyline/polygon extensions are real but should
   wait for a placement that would actually need them, to avoid building
   against a still-moving target.

---

## Appendix: reproducing this analysis

```
cd packages/temper-placer
PYTHONPATH=<worktree>/packages/temper-placer/src <python-with-temper_design_bundle_python> \
  <path-to>/isolation_barrier_analysis.py
```

The script (kept alongside this doc's provenance, not committed as
production code) parses `pcb/temper.kicad_pcb` via
`temper_placer.io.kicad_parser.parse_kicad_pcb`, classifies pads via
`elec/domain_manifest.yaml` through `temper_placer.io.real_board._load_manifest`,
computes world pad positions via `temper_placer.core.pin_geometry.pin_world_position`,
and runs the straight-line search, Delaunay bichromatic-cycle test, convex-hull
containment test, and stepped-polyline sweep described above.
