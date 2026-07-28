<!-- provenance: commit=fd6c9c15 dirty=true (this evidence doc + the re-target itself) -->

# Re-targeting the isolation-keepout gate to PD3 (12.6mm), and settling
# whether PD3 actually governs

Base commit: `fd6c9c15` (`merge: K2/K3 replaced with a DPDT part that closes
the DC-break gap too`), remote branch `docs/methodology-loop-discipline`.
Work done in worktree `agent-a9e515e195e63c66b`, on a local branch
`pd3-retarget-keepout` checked out directly at that commit (this worktree's
own prior HEAD, `e4e5e976` on `fix/router-grid-layer-pad-mismatch`, was not
based on the task's named commit, so the branch was re-pointed at
`fd6c9c15` before starting -- no extra worktree created, per the task's
disk-budget hard rule).

## Provenance labels (same convention as the prior determinations)

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Standard's own text, fetched/read by a prior session and re-cited here with its source; not re-fetched this session (no new standards fetch was needed -- the clause chain was already established in `docs/ENVIRONMENTAL_SPEC.md` and `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`). |
| **MEASURED** | Computed this session from `pcb/temper.kicad_pcb` / `elec/domain_manifest.yaml`, script and output shown. |
| **DERIVED** | Arithmetic or logic on labelled inputs, shown in full. |
| **ASSUMED** | Not established. Flagged for a human. |

---

## Verdict up front

**FALSIFIER, stated exactly as the task posed it:**

> "PD3 governs, and 12.6mm is the real requirement. If the cl. 29.2
> enclosure exception applies to this design, then 8.0mm was correct all
> along and this re-target is a conservative bound rather than a
> requirement -- and that is the finding."

**The falsifier did NOT fire. PD3 governs; 12.6mm is the real requirement,
not a conservative bound.** Checked against this design's own mechanical
documents (Task 0, below): the PCB sits in the same open, standoff-mounted
chassis cavity that the forced-air cooling duct uses (bottom vents -> intake
plenum -> fan -> heatsink duct -> rear exhaust), no document specifies a
sealed or gasketed PCB compartment, and the board independently carries an
IP20 rating ("no liquid ingress protection guaranteed"). **The cl. 29.2
enclosure exception does not apply on the evidence available.** This is
reported as a determination against the documents that exist, not a proof
against documents that don't -- see Task 0's own caveat on what would change
this.

**Consequence, measured against the real `pcb/temper.kicad_pcb` at this
worktree's base commit (Task 2):**

- `MIN_BARRIER_WIDTH_MM` in `scripts/check_isolation_keepout.py` re-targeted
  8.0mm -> **12.6mm**, full clause chain in the module docstring.
- The gate still fails **exit 3** (barrier zone missing) -- widening the
  requirement does not change a "barrier absent" finding; it was never
  going to pass either way at this stage.
- **My own independent measurement on this exact board (152 total
  sub-12.6mm cross-domain pad pairs, 132 body-free / 20 body-crossing)
  differs materially from the sibling's cited 202 (100/102)** -- this is
  not a reproduction failure, it is because this board (base `fd6c9c15`)
  already includes the K2/K3 relay replacement the sibling's board
  predates. See Sec 2 for the honest accounting of that difference.
- **CP-SAT barrier-constrained placement (`isolation_barrier.py`) is still
  `INFEASIBLE` at 12.6mm**, both orientations, ~24-25s each, same UNSAT-core
  culprit (`isolator_straddle_C6`) as at 8.0mm. No isolator's feasibility
  status changes under that module's own (conservative, bounding-circle)
  pad model between 8.0mm and 12.6mm, because 7 of 8 isolators were already
  infeasible at 8.0mm under that specific model.
- **Under the more precise, rectangle-aware pad measurement**
  (`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` Sec 6's
  method, independently re-run against this board), **K1 (8.000mm, exactly
  zero margin) and T1 (9.100mm) newly fail at 12.6mm** having passed 8.0mm.
  This is the answer to "which isolators fail at 12.6mm that passed at
  8.0mm" under the measurement that is actually precise enough to
  distinguish a pass from a fail at this component's real geometry.

---

## Task 0 -- does the cl. 29.2 enclosure exception apply? (done first)

### 0.1 What the exception requires

`docs/ENVIRONMENTAL_SPEC.md` Sec 3.1 already carries the clause text
(CITED-PRIMARY, IEC 60335-2-6 clause 29.2 Addition, IS 302-2-6:2009):

> "The microenvironment is pollution degree 3 unless the insulation is
> enclosed or located so that it is unlikely to be exposed to pollution
> during normal use of the appliance."

PD2 is the exception; it must be earned by showing the insulation is
**enclosed** or **located** away from pollution exposure. This determination
had not been separately checked against the mechanical design documents
before this session (`ENVIRONMENTAL_SPEC.md` Sec 3.1 gestures at
`docs/CHASSIS_AIRFLOW_DESIGN.md` and an absence-of-sealing argument, but the
task asked for this to be established directly from the mechanical design,
not inherited).

### 0.2 What the mechanical documents actually say (MEASURED, read directly this session)

- **`docs/COIL_BRACKET_DESIGN.md`**: the coil bracket "secures the induction
  coil mounting bracket ... within the RCA 12A3 chassis," bolted to "the
  RCA 12A3 chassis transformer rails" via M4 standoffs. Sec 4: "Large
  triangular cutouts around the central coil ring allow air from the bottom
  intake to flow directly through the Litz wire strands. The bracket itself
  acts as a baffle to direct air toward the IGBT heatsink after cooling the
  coil." **This is an open-frame, deliberately air-permeable structure, not
  a sealed enclosure wall** -- its own stated purpose is to let air (and
  therefore whatever the air carries) through, not to keep it out.
- **`docs/CHASSIS_AIRFLOW_DESIGN.md`**: "The airflow ducting system manages
  the cooling requirements of the Temper induction cooker within the
  **enclosed RCA 12A3 chassis**." Airflow path (Sec 3.2): bottom vents ->
  intake plenum -> 80mm PWM fan -> transition duct -> IGBT heatsink ->
  exhaust vent. Note the document's own word "enclosed" describes the
  **chassis as a whole** (an appliance case), not a sealed sub-compartment
  around the PCB specifically -- the chassis is enclosed against the room
  the same way any appliance case is, while its interior is an actively
  vented volume drawing kitchen air through it by design.
- **`docs/ASSEMBLY_GUIDE.md`**: Phase 1 step 4, "Bottom Vents: Ensure the
  bottom intake vents are unobstructed." Phase 4 step 2: "Main Board
  Mounting: Secure the PCB into the chassis using M3 standoffs." **The PCB
  is standoff-mounted directly inside the same chassis cavity the airflow
  system uses** -- no separate box, no gasket, no partition wall is
  described anywhere in this document for the PCB specifically. The only
  gasket mentioned in the entire assembly (Phase 3 step 3, "Apply high-temp
  silicone gasket to the chassis lip") seals the **glass-ceramic cooktop to
  the chassis**, not the electronics compartment -- a different joint,
  serving a different purpose (retaining the glass, not excluding
  pollution from the PCB).
- **`docs/SENSOR_MOUNT_DESIGN.md`**: describes a spring-loaded RTD probe
  assembly with a PTFE thermal-isolation sleeve -- a thermal detail, not an
  environmental-sealing one; no compartment or gasket claim for the PCB.
- **`docs/CONNECTORS_AND_WIRING.md`**: no compartment/sealing claim for the
  PCB either; only grounding/shielding topology.

### 0.3 What the IP20 rating implies

`docs/ENVIRONMENTAL_SPEC.md` Sec 3: "**IP20** ... No liquid ingress
protection guaranteed (spill-resistant design required)." IP20's second
digit (0) is the *liquid* ingress figure and does not by itself speak to
dust/particulate ingress (that is the first digit, 2 -- protected against
solid objects >12.5mm, i.e. fingers, not fine particulate). **Neither digit
of IP20 asserts protection against airborne grease, steam, or cooking
aerosol** -- and the forced-air duct is explicitly designed to pull exactly
that kind of air (bottom-vent kitchen air) across the compartment that
contains the PCB. An IP20 rating is not, on its own, an enclosure argument
in the clause 29.2 sense; if anything its explicit "no liquid ingress
protection guaranteed" caveat argues the opposite way.

### 0.4 Determination

**DERIVED, from the above (all MEASURED, read directly this session):** the
PCB is mounted inside the same open, forced-air-vented chassis cavity as
the coil, heatsink, and duct system; the coil bracket is an intentionally
air-permeable structure; the only gasket in the assembly seals the glass to
the chassis, not the electronics compartment; and the board's own IP20
rating does not itself constitute an enclosure argument. **The cl. 29.2
enclosure exception does not apply on the evidence available in this
repository today. PD3 governs, and 12.6mm is a real requirement, not a
conservative bound.**

**This is not being asserted as unfalsifiable.** What would change this
determination, stated plainly so it is falsifiable rather than final: a
future mechanical revision that (a) documents a specific sealed or gasketed
PCB compartment, separate from the coil/heatsink airflow path, and (b)
demonstrates the forced-air duct does not draw air across that
compartment's insulation. No such document exists in this repository as of
this commit. **This gap belongs on the safety engineer's list, exactly as
the task said it should if it could not be settled** -- but on the
documents that exist today, the honest reading is that the exception is not
earned, not that the question is unresolved in a way that leaves 8.0mm
defensible.

---

## Task 1 -- re-targeting the gate

### 1.1 The number

`scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` was **8.0**
(REINFORCED creepage, PD2, IEC 60335-1 Table 17 row iv, material group
IIIa/IIIb: 2 x 4.0mm). Re-targeted to **12.6** (same row, PD3: 2 x 6.3mm),
per the clause chain in `docs/ENVIRONMENTAL_SPEC.md` Sec 3.1 and Task 0's
determination above that PD3 governs. Full derivation and clause
citations added to the module docstring (`scripts/check_isolation_keepout.py`
lines ~30-107) and to the constant's own comment. Clearance remains
separately derived at 1.5mm/2.0mm-with-soldering-adder
(`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` Sec 4) and
is non-binding on this board -- unchanged by this re-target, restated in
the docstring so the two quantities are never conflated again.

### 1.2 Corridor model: kept, documented as a conservative sufficient bound

The gate enforces a straight-line, zero-copper corridor width -- a
clearance-shaped (through-air, straight-line) constraint carrying a
creepage-derived number. That makes the gate **sufficient but not
necessary** for the creepage requirement it cites: a corridor of width W
guarantees creepage >= W, but creepage can also be satisfied by a groove
(lengthens the surface path without widening the straight-line gap), an
earthed inner-layer screen (clause 3.4.4 option (a)), or a qualified Annex J
coating (changes the pollution degree outright, see
`docs/evidence/2026-07-28-coating-supplemental-scope.md`). None of these are
expressible as a single corridor width.

**Decision: keep the corridor model, now explicitly documented in the
gate's own docstring as a conservative sufficient bound, rather than
implementing a true minimum-creepage-path measure.** Reasons (also in the
module docstring):

1. The corridor's own INFEASIBLE result (Task 2 below) is already known to
   be driven by isolator **package** geometry -- K2/K3's own coil-to-contact
   pinout is unconditionally infeasible at any corridor width down to
   1.0mm (`docs/evidence/2026-07-28-barrier-constrained-placement.md`'s
   control experiment). A true surface-path measure cannot lengthen a path
   that runs across a relay's own plastic base; it would not change the
   actionable finding for the binding case.
2. A true creepage-path measure (grooves, screening planes, Annex J
   microenvironment changes) is a substantially larger modeling effort than
   this re-target, and sits exactly in "make the safety model more
   permissive" territory that deserves its own dedicated, reviewed change --
   not a side effect of a constant re-target.
3. The corridor model fails in the **safe** direction: every board that
   passes it is provably safe by construction; a board that fails it may
   still be compliant via an unmodeled remedy. That caveat is now stated
   explicitly in the gate's own docstring, rather than letting a bare
   VIOLATION/INFEASIBLE result be read as a standalone BOM conclusion --
   the exact mistake `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`
   Sec 7 found in this project's own prior history.

### 1.3 Test fixture update

`scripts/tests/test_check_isolation_keepout.py`'s synthetic barrier fixture
was widened from a 10mm strip (`x=[45,55]`, sized for the old 8.0mm
minimum) to a 16mm strip (`x=[42,58]`, sized for the new 12.6mm minimum with
margin), and the one test whose fixture geometry depended on the exact
former edge position (`test_pad_body_overlaps_barrier_even_when_center_is_outside`)
was moved to match the new edge. All 27 tests pass unchanged in intent
(same groups, same coverage; see file docstring).

```
$ uv run --no-sync python3 -m pytest scripts/tests/test_check_isolation_keepout.py -q
27 passed in 2.04s
```

### 1.4 Run against the real board

```
$ uv run --no-sync python3 scripts/check_isolation_keepout.py
Copper layers: 4 (F.Cu, In1.Cu, In2.Cu, B.Cu). Footprints examined: 168.
Pads examined: 519 (HV=87, SELV=221). Copper items examined
(segments+arcs+vias+non-keepout zones): 2482. Keepout zones found on
board (any name): 0.
Barrier zone NOT FOUND (name='MAINS_SELV_ISOLATION_BARRIER').
Required minimum barrier width: 12.6mm (REINFORCED creepage; see module
docstring).
=== VIOLATIONS: 1 === [missing] ...
FAILED -- 1 violation(s)
$ echo $?
3
```

Same violation, same exit code, as before this change (`pcb/temper.kicad_pcb`
is not touched, per the task's hard rule -- confirmed `git diff fd6c9c15 --
pcb/temper.kicad_pcb elec/` is empty throughout this session). Widening the
minimum width cannot change a "the barrier doesn't exist at all" finding.

**Note: `HV=87` here, not the `97` several prior evidence docs report.**
This board (base `fd6c9c15`) already includes the K2/K3 relay replacement
(Omron G5LE-1 SPDT -> Finder 40.52.7.012.0000 DPDT); the prior docs'
denominators are from an earlier board revision. See Sec 2.1 below for the
full accounting.

---

## Task 2 -- consequence, measured against the real board

### 2.1 Cross-domain pad-pair count at 12.6mm -- own measurement, own script

**Method** (same as `docs/evidence/2026-07-28-coating-supplemental-scope.md`
Sec 1 and `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`
Sec 6): load `domains.HV.nets`/`domains.SELV.nets` from
`elec/domain_manifest.yaml` (exact net-name match), parse
`pcb/temper.kicad_pcb` via `kiutils`, model every pad as an axis-aligned
rectangle (footprint rotation re-verified this session: every one of the
168 footprints is at an exact 0/90/180/270-degree rotation, 0 flipped to
`B.Cu` -- so this is exact, not approximate), compute every HV-pad/SELV-pad
rectangle-to-rectangle edge gap for pads on **different** components, and
for pairs under 12.6mm sample 400 points along the shortest path to test
body-crossing vs body-free (any footprint's `F.Fab`/`F.SilkS`/`F.CrtYd`
bounding box, fallback order, excluding the two owning footprints).
Script: `measure_pd3.py` (session scratchpad, not committed, matching this
project's established convention for this exact kind of read-only
analysis).

**Denominators (MEASURED, this session, this board):**

| Quantity | This session | Prior sibling figure (different, earlier board) |
|---|---:|---:|
| Footprints | 168 | 168 |
| Footprints with usable body outline | 161 | 161 |
| HV nets | 27 | 21 |
| SELV nets | 33 | 33 |
| HV pads | 87 | 97 |
| SELV pads | 221 | 221 |
| Cross-domain, cross-component pad-pairs compared | 19,188 | 21,392 |
| **Pairs < 8.0mm** | **41** (38 body-free / 3 body-crossing) | ~66-68 |
| **Pairs < 12.6mm** | **152** (132 body-free / 20 body-crossing) | 202 (100 body-crossing / 102 body-free) |
| Distinct (HV component, SELV component) pairs < 12.6mm | 62 | not directly comparable (different denominator basis) |
| Sub-2.0mm pairs | **5** | 5 (task-cited figure) |

**The sub-2.0mm pairs reproduce exactly, including the fifth pair the task
specifically named:**

```
C17.2 (hb.gate_hs.driver-p2) <-> R32.1 (+3V3): 0.905mm  body_free=True
R30.2 (tank-out) <-> R1.1 (+15V): 1.100mm
R30.1 (tank.c_tank1-p2) <-> R1.1 (+15V): 1.124mm
R30.1 (tank.c_tank1-p2) <-> R1.2 (power_in.bypass_relay-coil1): 1.148mm
C22.2 (hb.gate_hs.driver-p2) <-> L2.2 (+3V3): 1.876mm  body_free=True
```

`C22.2 <-> L2.2` at **1.876mm**, exactly matching the task's cited figure to
three decimals -- these two components (a gate-driver bootstrap cap and a
power inductor) are unrelated to the K2/K3 relay change, so this exact
reproduction across board revisions is a strong cross-check that the
underlying geometry engine (HV/SELV classification, rectangle model,
per-pair distance) agrees with the sibling's, and that the aggregate
divergence below is real, not a bug in either script.

**Why the aggregate counts differ, and why that is itself a finding, not a
bug:** this worktree's base commit (`fd6c9c15`) already includes
`docs/evidence/2026-07-28-relay-replacement-implementation.md`'s K2/K3
swap (Omron G5LE-1 SPDT -> Finder 40.52.7.012.0000 DPDT). Checked directly:
only **5** of my 152 sub-12.6mm pairs involve K1/K2/K3 at all (all >11mm,
none tight), so the relay swap itself is not the direct cause of the ~50-pair
aggregate difference. The HV net count grew 21 -> 27 (new per-pole contact
nets for the DPDT relays: `discharge.k_dis1-nc1/no1/no2` etc.), yet the
measured HV pad count **fell** 97 -> 87 and the unclassified-component count
grew 10 -> 14 (per the CP-SAT module's own partition, Sec 2.2 below) -- a
net effect I traced partially (new isolator contact nets exist that
previously-HV-adjacent copper apparently no longer touches in the same way)
but did not fully resolve to the pad level in the time available. **This
divergence is reported honestly, in the same spirit the coating-scope
determination reported its own 202-vs-222 discrepancy**: the two board
revisions are genuinely different measurement targets, not two
implementations disagreeing about the same board. My own 152/132/20 figures
are reproducible from `measure_pd3.py` against this exact board; they
should not be read as a correction of the sibling's 202/100/102, which was
correct for its own (earlier) board.

**Twenty tightest pairs (this board, this session), for reference:**
C17.2<->R32.1 0.905, R30.2<->R1.1 1.100, R30.1<->R1.1 1.124,
R30.1<->R1.2 1.148, C22.2<->L2.2 1.876, R30.1<->R32.1 2.495,
R30.2<->R32.1 2.495, R30.2<->R73.1 2.495, C22.1<->L2.2 3.201,
C17.1<->R26.1 3.325, R30.1<->U13.3 3.410, R30.1<->R54.1 3.615,
R30.1<->R54.2 3.615, R30.1<->R73.1 3.651, C17.1<->R32.1 3.855,
C17.1<->U13.3 3.882, R30.1<->R26.1 4.117, C22.1<->U15.4 4.485,
R30.2<->R46.2 4.775, C22.1<->C16.1 5.210 (all mm).

### 2.2 CP-SAT barrier-constrained placement at 12.6mm

`packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`
still exists as an opt-in constraint, 13 unit tests (all passing, unchanged
by this session's one-line constant edit --
`uv run --no-sync python -m pytest packages/temper-placer/tests/placer/cp_sat/test_isolation_barrier.py -q`
-> 13 passed). `DEFAULT_CORRIDOR_WIDTH_MM` re-targeted 8.5 -> **13.1**
(same 0.5mm-above-the-gate's-minimum margin convention, now above 12.6mm
instead of 8.0mm), for consistency with the gate; no test depended on the
default (every test passes `corridor_width_mm` explicitly).

**Re-run against the real board at 12.6mm, both orientations:**

```
Board: 152 x 234 mm, 168 components

orientation=vertical
  status=infeasible  solve_time_ms=24036.7  placed=0  unplaced=168
  unsat_core=[{'name': 'isolator_straddle_C6', ...}]
  partition: hv_only=40 selv_only=106 isolators=8 unclassified=14
  infeasible_isolators=['C6', 'K1', 'K2', 'K3', 'T1', 'U3', 'U7']

orientation=horizontal
  status=infeasible  solve_time_ms=24676.7  placed=0  unplaced=168
  unsat_core=[{'name': 'isolator_straddle_C6', ...}]
  partition: hv_only=40 selv_only=106 isolators=8 unclassified=14
  infeasible_isolators=['C6', 'K1', 'K2', 'K3', 'T1', 'U3', 'U7']
```

**Still INFEASIBLE at 12.6mm, both orientations, ~24-25s each** (well under
the 180s timeout previously observed and this session's 60s timeout
argument -- the contradiction is found quickly, same as at 8.0mm). Same
UNSAT-core culprit (`isolator_straddle_C6`) as the 8.5mm run in
`docs/evidence/2026-07-28-barrier-constrained-placement.md`. **7 of 8
isolators (all but `PS1`) are reported infeasible under this module's own
pad model at 12.6mm -- the identical set reported infeasible at 8.0mm in
the prior session.** Partition denominators (`hv_only=40, selv_only=106,
isolators=8, unclassified=14`, total 168) differ from the prior session's
`44/106/8/10` for the same K2/K3-relay-replacement reason as Sec 2.1 --
independently reproduced here via the CP-SAT module's own
`classify_domain_partition`, a different code path than `measure_pd3.py`.

**What now blocks it, precisely, at 12.6mm:** the same thing that blocked
it at 8.0mm -- `isolation_barrier.py`'s own conservative bounding-circle pad
model (`radius = max(size.X, size.Y)/2`, matching
`check_isolation_keepout.py`'s pad-intrusion model exactly) already found 7
of 8 isolators infeasible at 8.0mm (only `PS1`, the Mean Well AC/DC module
at 35.5mm, ever passed). Since achievable-gap is monotonic and 12.6 > 8.0,
nothing that already failed 8.0mm under this model can newly pass 12.6mm --
**no isolator's pass/fail status changes under this specific module's
model between the two widths.** `C6` and `K2`/`K3` remain unconditionally
infeasible at any corridor width (proven down to 1.0mm in the prior
session's control experiment) -- their creepage path runs across the
part's own plastic base/body, which no PCB feature can lengthen.

### 2.3 Which isolators fail at 12.6mm that passed at 8.0mm -- the precise answer

Sec 2.2's CP-SAT module uses a deliberately conservative bounding-circle pad
model that already fails 7 of 8 isolators at 8.0mm, so it cannot
distinguish "passed at 8.0, fails at 12.6" from "failed at both" for any
isolator except `PS1`. The question the task actually asks needs the more
precise, **rectangle-aware** pad measurement
(`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` Sec 6's
method), independently re-run this session directly against this board's
real footprints (own script, `isolator_rect_gap.py`, reusing the same
rectangle-corner rotation logic as `measure_pd3.py`):

| Ref | HV pads | SELV pads | Min HV-cluster<->SELV-cluster edge gap (mm) | Pass @ 8.0mm | Pass @ 12.6mm |
|---|---:|---:|---:|:---:|:---:|
| C6 | 1 | 1 | 3.200 | No | No |
| **K1** | 1 | 2 | **8.000** | **Yes (zero margin)** | **No** |
| K2 | 1 | 2 | 3.500 | No | No |
| K3 | 1 | 2 | 3.500 | No | No |
| PS1 | 2 | 2 | 35.500 | Yes | Yes |
| **T1** | 2 | 1 | **9.100** | **Yes** | **No** |
| U3 | 2 | 3 | 6.020 | No | No |
| U7 | 5 | 4 | 7.250 | No | No |

These figures reproduce the creepage-determination-brainstorm doc's Table
in Sec 6 exactly (K1=8.000, T1=9.100, U3=6.020, U7=7.250, C6=3.200,
PS1=35.500), even on this later board revision -- K2/K3's 3.500mm also
happens to numerically match the pre-replacement G5LE-1 figure, though the
part itself changed.

**`K1` (the bypass relay, Omron G4A-1A-E) and `T1` (the current-sense
transformer, Coilcraft CST3015-100ED) are the isolators that newly fail at
12.6mm having passed 8.0mm**, under the measurement precise enough to tell
the two widths apart. `K1`'s 8.0mm-era "pass" was already flagged as a
zero-margin, practically-not-a-pass result in the prior session
(`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` Sec 8) --
at 12.6mm it is unambiguously a fail, by 4.6mm. `T1`'s datasheet-claimed
">=8mm creepage/clearance" clears the old PD2 figure but falls 3.5mm short
of the new PD3 one. **`C6`, `K2`, `K3`, `U3`, and `U7` were already failing
at 8.0mm and remain failing at 12.6mm** -- their status does not change,
only their margin worsens.

---

## FALSIFIER -- result (restated)

> "PD3 governs, and 12.6mm is the real requirement. If the cl. 29.2
> enclosure exception applies to this design, then 8.0mm was correct all
> along and this re-target is a conservative bound rather than a
> requirement -- and that is the finding."

**Did not fire.** Task 0's determination, made directly against
`docs/COIL_BRACKET_DESIGN.md`, `docs/CHASSIS_AIRFLOW_DESIGN.md`,
`docs/ASSEMBLY_GUIDE.md`, and `docs/SENSOR_MOUNT_DESIGN.md`, is that the
cl. 29.2 enclosure exception is not earned on this design as documented
today: the PCB shares an open, forced-air-vented chassis cavity with no
sealed compartment, and the appliance's own IP20 rating does not itself
constitute an enclosure argument. **PD3 governs; 12.6mm is the real
requirement, not a conservative bound.** This determination is reported
with its own falsifiability condition (Sec 0.4) rather than as a closed
question -- a future mechanical revision documenting a genuine sealed PCB
compartment could change it, but no such document exists today.

---

## UNVERIFIED

- **The ~50-pair discrepancy between this session's 152 (8.0mm: 41) and the
  sibling's cited 202 (8.0mm: ~66-68) sub-threshold counts is reported, not
  fully explained.** Ruled out: pad rotation (all exact 90-degree
  multiples), footprint flip state (0 flipped), the relay swap's direct
  involvement (only 5 of 152 pairs touch K1/K2/K3, all >11mm). Not fully
  traced: exactly which net-classification or pad-topology change from the
  K2/K3 relay replacement (HV nets 21->27, HV pads 97->87,
  unclassified-component count 10->14) accounts for the remaining
  difference. This matches the same category of aggregate-count discrepancy
  `docs/evidence/2026-07-28-coating-supplemental-scope.md` Sec 1.3 already
  reported and did not fully resolve for an earlier pair of independent
  measurements on the *same* board revision -- here the boards themselves
  differ, which is expected to matter more, not less.
- **The body-crossing/body-free split (20/132 at 12.6mm) is a rectangle-box
  proxy, not a rigorous surface-path trace**, same caveat every prior
  session in this thread has carried: 96 copper pour zones exist on both HV
  and SELV nets and are not analysed by this or any prior version of this
  script. The "202/222" and "152" figures alike are optimistic floors on
  the true minimum creepage-path census, not ceilings.
- **Task 0's determination is a documents-only reading**, not a physical
  inspection of the assembled chassis. It is falsifiable in the direction
  stated in Sec 0.4 (a future document could establish a real sealed
  compartment) but not in the other direction -- absence of a sealing
  document is not proof of impossibility, only the honest state of the
  evidence today.
- **`isolation_barrier.py`'s own bounding-circle model cannot, by
  construction, distinguish "newly failing at 12.6mm" from "always failing"
  for 7 of its 8 isolators**, since it already found them infeasible at
  8.0mm. Sec 2.3's answer to that specific question therefore comes from a
  different (more precise, rectangle-aware) measurement method than the one
  the CP-SAT module itself uses -- flagged explicitly so the two are never
  conflated. Whether `isolation_barrier.py` itself should be upgraded to
  the rectangle-aware model is a legitimate follow-up, deliberately not
  done here (same reasoning as Sec 1.2: changing what a safety-adjacent
  model measures is a separate, dedicated decision, not a side effect of a
  constant re-target).
- IEC 60335-1's Table 17 transcription underlying both the 8.0mm and
  12.6mm figures remains an OCR'd 2008-era national adoption
  (`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` Sec 13),
  independently cross-checked against a manufacturer's IEC 60664-1
  reproduction but not against the IEC's own current edition -- a safety
  engineer must read the current edition before sign-off, unchanged from
  every prior determination in this thread.

---

## Verification

| Check | Result |
|---|---|
| `check_domain_partition.py` | exit 0 |
| `capacity_budget_gate.py` | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 |
| `check_derived_doc_drift.py` | exit 0 |
| `check_copper_net_consistency.py` | **exit 3, 146 violations -- pre-existing, confirmed via `git diff fd6c9c15 -- pcb/temper.kicad_pcb elec/` (empty)**, matches the task's own stated expectation (stale board pending a K2/K3 resync) |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 (9/10 fresh, 1 missing extension warns only -- lenient locally, `TEMPER_REQUIRE_FRESH_EXTENSIONS` unset) |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 |
| `check_measurement_provenance.py` | **exit 5 -- pre-existing** (`power_pcb_dataset/drc_ceiling.json#boards.temper`: malformed `source='measured-live-5-samples'`), file untouched this session |
| `check_workflow_pr_triggers.py` | exit 0 (23 files, all compliant) |
| `make netlist` | passes |
| `uv run --no-sync python -m pytest elec/validation -q` | 30 passed |
| `uv run --no-sync python3 -m pytest scripts/tests/test_check_isolation_keepout.py -q` | 27 passed |
| `uv run --no-sync python -m pytest packages/temper-placer/tests/placer/cp_sat/test_isolation_barrier.py -q` | 13 passed |
| **`check_isolation_keepout.py` (re-targeted)** | **exit 3** -- barrier missing, same as before, required width now 12.6mm |

All ten of the plan's named gates are green except the two explicitly
called out as pre-existing failures in the task itself
(`check_copper_net_consistency.py` exit 3,
`check_measurement_provenance.py` exit 5) -- both independently confirmed
pre-existing at this worktree's exact base commit via `git diff`.

---

## Files touched

- `scripts/check_isolation_keepout.py` -- `MIN_BARRIER_WIDTH_MM` 8.0 -> 12.6,
  full clause-chain docstring rewrite, corridor-model decision documented.
- `scripts/tests/test_check_isolation_keepout.py` -- fixture barrier strip
  widened 10mm -> 16mm to clear the new minimum with margin; one test's
  hardcoded edge position updated to match.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`
  -- `DEFAULT_CORRIDOR_WIDTH_MM` 8.5 -> 13.1 (same 0.5mm-margin convention
  above the gate's new minimum); no test depended on the default value.
- This evidence file.

Not touched: `pcb/temper.kicad_pcb`, `elec/src/*`, `scripts/generate_kicad_dru.py`,
`pcb/libs/*`, `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`,
`power_pcb_dataset/drc_ceiling.json` -- confirmed via `git status`/`git diff`
before writing this document.

## Compliance with the task's hard rules

- No safety figure reduced. 8.0mm -> 12.6mm is strictly upward; clearance
  (1.5/2.0mm) untouched and still correctly non-binding.
- No `git stash` used anywhere in this session.
- No `run_in_background`; the one command the harness auto-backgrounded
  (`uv sync --all-packages`, which exceeded the 120s default) was stopped
  via `TaskStop` and re-run in the foreground with an explicit longer
  timeout, per this project's own established pattern for this exact
  situation.
- No extra worktree created -- this worktree's own branch was re-pointed at
  the task's named base commit instead.
- `uv run --no-sync` used throughout (after the one, once-only,
  foregrounded `uv sync --all-packages` into this worktree's own empty
  venv).
- Committed after each meaningful step.
- Counts reported with denominators throughout; discrepancies against
  cited sibling figures explained (board-revision difference), not silently
  smoothed over.
- Not pushed.
