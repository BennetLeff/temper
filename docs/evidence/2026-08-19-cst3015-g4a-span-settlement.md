# The CST3015 span is 9.100 mm and the G4A-E span is 8.000 mm — T2 clears its 8.0 mm figure

**Date:** 2026-08-19
**Scope:** analysis only. Nothing was modified. `pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified identical
before and after every measurement, never opened for write. No `elec/**/*.ato` edited. No
threshold, clearance, creepage, ampacity, DRU, ratchet, ceiling, allowlist or oracle
touched. No datasheet value or part number is invented anywhere below.

**Re-run:**

```
env -u CONDA_PREFIX make venv-isolate
.venv/bin/python docs/evidence/2026-08-19-cst3015-g4a-span-settlement.py pcb/temper.kicad_pcb
.venv/bin/python scripts/measure_cross_domain_creepage.py --min-creepage-mm 9.5 --limit 400
```

---

## 1. The verdict

| package | ref | intra-package HV↔SELV copper span | binding pad pair |
|---|---|---:|---|
| Coilcraft CST3015 | T1 | **9.100 mm** | pad 1 (`tank-out`) ↔ pad 4 (`gnd`) |
| Coilcraft CST3015 | T2 | **9.100 mm** | pad 1 (`hb-gnd`) ↔ pad 4 (`gnd`) |
| Omron G4A-E relay | K1 | **8.000 mm** | pad 13 (`power_in.ntc-no`) ↔ pad A1 (coil1) |

`analysis/t1-sense-node-relocation` (`5e53ceaa0`) is **right**: 9.100 mm.
`analysis/per-pairing-placer-solve` (`30edd0a93`) is **wrong**: 7.800 mm on the CST3015 and
5.425 mm on the G4A-E are artifacts of a non-rigid transform, not measurements of copper.

**Consequence.** T2's `DC_BUS↔SELV` requirement is a fully determinate **8.0 mm**. T2's
copper spans **9.100 mm**. **T2 PASSES, with 1.100 mm of margin.** It is not short by
0.200 mm, there is no BOM or topology problem to solve, and Task 2 of this investigation
does not arise. **T1 is the sole remaining placement blocker.**

---

## 2. Why 9.100 / 8.000 is right

### 2.1 The intra-package span is a rigid-body invariant

Every pad of one footprint is carried by the *same* rigid motion. The copper-to-copper
distance between two pads **of the same footprint** therefore cannot depend on where the
part sits or how it is rotated — it is a package constant. Both disputing branches assert
this in their own prose; only one transform actually obeys it.

Evaluated with `core.pad_geometry.pad_pair_distance` (the exact Minkowski-sum kernel the
REQ-SAFE-01 validator and `scripts/check_isolation_keepout.py` both use), rotating each
footprint rigidly through 0°, 90°, 180°, 270° **and a deliberately non-square 37°**:

| ref | rigid transform | sheared transform (position rotated, body left behind) |
|---|---|---|
| T2 | 9.1000 9.1000 9.1000 9.1000 9.1000 — **invariant** | 9.1000 **7.8000** 9.1000 **7.8000** — *not invariant* |
| T1 | 9.1000 9.1000 9.1000 9.1000 9.1000 — **invariant** | **7.8000** 9.1000 **7.8000** 9.1000 — *not invariant* |
| K1 | 8.0000 8.0000 8.0000 8.0000 8.0000 — **invariant** | 8.0000 **5.4250** 8.0000 **5.4250** — *not invariant* |

A quantity that changes when a rigid body is rotated is not a distance. Failing this test
is by itself disqualifying, independently of any argument about KiCad file semantics.

### 2.2 KiCad's semantics, resolved rather than bounded

In a `.kicad_pcb` file a pad's `(at x y ANGLE)` carries a **footprint-local, unrotated
position** and an **absolute world orientation**. The parent footprint's angle is added to
the *position* at load time but **never** to the *angle*. This is stated in-tree by
`scripts/check_pad_orientation.py` lines 5–11 — it is the exact convention that gate exists
to police — and it is what `scripts/measure_cross_domain_creepage.py` implements.

The board's own bytes confirm it. Both library footprints carry **no pad angle at all**
(`pcb/libs/temper.pretty/CST3015.kicad_mod`, `Relay_SPST_Omron-G4A-E.kicad_mod` — every pad
is at 0). The placed instances read:

| ref | footprint angle | every pad's absolute angle | meaning |
|---|---:|---:|---|
| T2 | 0° | 0° | identity — library geometry verbatim |
| T1 | 90° | 90° | the footprint rotation **did** reach the pads: a faithful rigid placement |
| K1 | 0° | 180° | 180° is a symmetry of every K1 pad shape (axis-aligned `rect`/`circle`) — moves no copper |

So both CST3015 instances and the relay present exactly the library geometry. Computed
straight off the library land pattern (primary pads 9.0 × 4.8 mm at y = −6.85, secondary
pads 3.0 × 4.6 mm at y = +6.95):

```
pad 1 near edge  = -6.85 + 4.8/2 = -4.45
pad 4 near edge  = +6.95 - 4.6/2 = +4.65   (x ranges overlap)
span             =  4.65 - (-4.45) = 9.100 mm
```

which is precisely the hand computation `5e53ceaa0` performed. (That commit transposed the
labels "y-min"/"y-max", but the numbers and the result are correct, and the method is valid
for this footprint precisely because every CST3015 pad's footprint-relative angle is 0.)

For K1: coil pad Ø1.8 mm at y = 0, Faston tab 6.35 × 1.2 mm at y = 9.5 →
`(9.5 − 0.6) − 0.9 = 8.000 mm`. This independently reproduces the figure recorded in
`core/pad_geometry.py`'s own `pad_pair_distance` docstring, which cites K1's pair as
**exactly 8.000 mm** against the 8.000 mm REINFORCED requirement (and notes that a polygon
approximation manufactures 7.9989 mm there). That docstring is an in-tree pin predating
this dispute and it agrees with 8.000, not 5.425.

### 2.3 Handedness does not matter here

KiCad rotates footprint children **clockwise in the Y-down frame**, i.e. `R(-θ)`
(`packages/temper-geometry/src/core_graph_geometry.rs:188-200`;
`parse_engine.rs`'s `rotate_local_to_world` comment). The settlement script evaluates every
pair under **both** `R(+θ)` and `R(-θ)` and gets identical figures, and
`scripts/measure_cross_domain_creepage.py` — which computes each pad position under both
conventions as a built-in sensitivity check — reports `convention_sensitive = False` for
every one of these pairs:

```
 8.0000  alt= 8.0000  conv_sensitive=False  K1.13(power_in.ntc-no) <-> K1.A1(coil1)
 8.0000  alt= 8.0000  conv_sensitive=False  K1.14(w1_2)            <-> K1.A2(coil2)
 9.1000  alt= 9.1000  conv_sensitive=False  T1.1(tank-out)         <-> T1.4(gnd)
 9.1000  alt= 9.1000  conv_sensitive=False  T1.2(PWR_RTN)          <-> T1.3(I_SENSE)
 9.1000  alt= 9.1000  conv_sensitive=False  T2.1(hb-gnd)           <-> T2.4(gnd)
 9.1000  alt= 9.1000  conv_sensitive=False  T2.2(DC_BUS_RTN)       <-> T2.3(s1)
```

The handedness question is **resolved and shown immaterial**, not bounded.

### 2.4 Five independent paths agree

1. Library `.kicad_mod` land patterns, by hand — 9.100 / 8.000.
2. Direct board-bytes reconstruction under KiCad semantics + `pad_pair_distance`, invariant at 0/90/180/270/37° — 9.100 / 8.000.
3. **`analysis/per-pairing-placer-solve`'s own committed `docs/evidence/2026-08-19-isolator-package-maxima.py`**, run unmodified against the board — `T1 9.1000`, `T2 9.1000`, `K1 8.0000`.
4. The placer parser with the canonical `comp_rot + pad_rotation_deg` composition, at all four rotation quadrants — 9.100 / 8.000.
5. Main-branch `scripts/measure_cross_domain_creepage.py` (gate-grade, reads the board directly using absolute pad angles) — `T1: worst gap 9.100mm`, `T2: worst gap 9.100mm`, `K1.13↔K1.A1 = 8.0000mm`.

Path 3 is decisive on its own: the branch that reported 7.800 mm ships a script that
reports 9.100 mm from the same kernel it cites.

---

## 3. Why 7.800 / 5.425 is wrong — the precise defect

`temper-design-bundle`'s parser stores (`packages/temper-design-bundle/src/parse_engine.rs:1722`):

```rust
let pad_rotation_deg = (pad_abs_rotation_deg.sub(&rot_deg)).to_f64().rem_euclid(360.0);
```

— i.e. `Pin.pad_rotation_deg` is **footprint-RELATIVE** (`absolute − footprint angle`), to
pair with `Pin.position`, which is likewise footprint-local. Measured on this board:

| ref | file absolute pad angle | footprint angle | `Pin.pad_rotation_deg` | `initial_rotation_quadrant` |
|---|---:|---:|---:|---:|
| T2 | 0° | 0° | 0.0 | 0 |
| T1 | 90° | 90° | **0.0** | 1 |
| K1 | 180° | 0° | 180.0 | 0 |

The world body angle is therefore `component_rotation + pad_rotation_deg`. That is exactly
what every other consumer in-tree already does:

- `router_v6/obstacle_map.py:313` — `total_angle = comp_angle + pad_rot_rad`
- `router_v6/kicad_connectivity.py:277` — `rotation = comp_rot_deg + pad_rotation_deg`
- `placer/cp_sat/tank_creepage.py:465` — `math.radians(q * 90) + math.radians(pin.pad_rotation_deg)`

`analysis/per-pairing-placer-solve` instead rotates each pad's **position** by the component
rotation while handing `pad_rotation_deg` **alone** to the pad **body**:

- `docs/evidence/2026-08-19-per-pairing-residual-attribution.py:42-50` (`wtup`) — position from `pin_world_position_at(pin, comp, pos, rot)`, body from `math.radians(pin.pad_rotation_deg)` with no `rot` term. This is the script the branch cites as the source of its 7.800 / 5.425 "exact copper" column.
- `docs/evidence/2026-08-19-per-pairing-creepage-measure.py:88-109` (`world_tup`) — same omission.
- `placer/cp_sat/isolation_barrier.py`'s `_worst_axis_radius` — includes the candidates `pad.axis_radius(axis, model_rot_rad)` and `pad.axis_radius(axis, pad_rot_rad)` alongside the correct `model_rot + pad_rot`.

That is a **shear, not a rotation**: the pads translate around the footprint origin while
their copper keeps pointing the old way. Driven through the parser it reproduces both
disputed figures exactly, and only at the odd quadrants:

```
ref    rot_q | comp_rot + pad_rot (canonical) | pad_rot alone (disputed)
T2         0 |                        9.1000 |                   9.1000
T2         1 |                        9.1000 |                   7.8000
T2         2 |                        9.1000 |                   9.1000
T2         3 |                        9.1000 |                   7.8000
T1         0 |                        9.1000 |                   9.1000
T1         1 |                        9.1000 |                   7.8000   <- T1 sits at quadrant 1
T1         2 |                        9.1000 |                   9.1000
T1         3 |                        9.1000 |                   7.8000
K1         0 |                        8.0000 |                   8.0000
K1         1 |                        8.0000 |                   5.4250
K1         2 |                        8.0000 |                   8.0000
K1         3 |                        8.0000 |                   5.4250
```

Arithmetically the loss is a pad half-extent swap: the CST3015 primary pad's
`(9.0 − 4.8)/2 = 2.10` mm minus the secondary's `(4.6 − 3.0)/2 = 0.80` mm gives the
**1.300 mm**; the relay tab's `(6.35 − 1.2)/2 = 2.575` mm gives the **2.575 mm**.

### 3.1 The reasoning error

Both helpers justify the omission with a statement that is *true of the file*:

> "the pad's own `(at x y angle)` rotation is ALREADY absolute in a `.kicad_pcb` file and is
> not composed with the footprint angle — the convention `scripts/check_pad_orientation.py`
> exists to police"

The premise is correct. It is applied to the wrong variable. `Pin.pad_rotation_deg` **no
longer holds the file's value** — the parser already subtracted the footprint angle one
layer down. Dropping the component rotation there does not *decline to compose*; it
*discards a rotation the pad positions have already received*. T1 is the clean
demonstration: its file angle is 90°, its parsed `pad_rotation_deg` is **0.0**.

### 3.2 The "largest of three candidates" bound is not sound for this quantity

`_worst_axis_radius` takes `max` over three candidate orientations on the argument that the
maximum is ≥ each, so the encoded gap can only over-constrain. Two problems:

1. **The composition is not ambiguous.** It is fixed by `parse_engine.rs:1722` and settled
   identically by three other in-tree consumers. There is one convention, and it is
   testable — as §2 does.
2. **A bound on a rigid-body invariant must itself be rotation-invariant.** The max is not:
   it returns 9.100/8.000 at quadrants 0 and 2 and 7.800/5.425 at 1 and 3. Inflating a pad's
   half-extent by an orientation the pad does not have is not conservatism about an unknown
   convention; it is a different, non-physical part. It is what let the model report
   T1/T2 at 7.000 mm — 2.100 mm below their real copper.

---

## 4. What this changes downstream

Correcting the composition and re-grading `30edd0a93`'s §3 table against the same
per-pairing figures (package maxima taken from that branch's own
`isolator-package-maxima.py`, run unmodified):

| ref | binding HV net | group | required | span reported by `30edd0a93` | **settled span** | verdict |
|---|---|---|---:|---:|---:|---|
| C6 | `PWR_RTN` | MAINS | 4.80 | 8.000 | **8.000** | PASS (unchanged) |
| K1 | `power_in.ntc-no` | MAINS | 4.80 | 5.425 | **8.000** | PASS (was PASS on a wrong number) |
| K2 | `discharge.k_dis1-nc` | DC_BUS | 8.00 | 12.760 | **12.760** | PASS (unchanged) |
| K3 | `discharge.k_dis2-nc` | DC_BUS | 8.00 | 12.760 | **12.760** | PASS (unchanged) |
| PS1 | `+170V_BUS` | DC_BUS | 8.00 | 35.500 | **35.500** | PASS (unchanged) |
| U6 | `hb-gnd` | DC_BUS | 8.00 | 8.100 | **8.100** | PASS, 0.100 margin (unchanged) |
| **T2** | `hb-gnd` | DC_BUS | 8.00 | 7.800 → FAIL by 0.200 | **9.100** | **PASS, 1.100 margin — verdict FLIPS** |
| **T1** | `tank-out` | TANK | 20.00 † | 7.800 → short ≥12.200 | **9.100** | **FAIL, short 10.900** |

† The 20.0 mm `SELV↔TANK` figure remains a **proven lower bound, not a requirement**: 47 kHz
is above IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling and cl. 2.3 routes dimensioning above
it to the unobtained IEC 60664-4. Nothing here derives, guesses or lowers it. T1's shortfall
is restated as 10.900 mm rather than ≥12.200 mm purely because the span it is measured
against was wrong; the requirement is untouched.

**The UNSAT core reported in `30edd0a93` — `{T1, T2}` — should be re-solved.** T2's
per-pairing need becomes `8.0 − 9.100 = −1.100` (it clears), so on the corrected geometry T2
is expected to drop out of the core, leaving T1 alone. That solve is **not** re-run here
(another agent holds the memory budget); it is a specific, cheap follow-up:
`row E` of that branch's ablation with T2 re-enabled and only T1 relaxed.

Two further figures in `30edd0a93`'s achieved-placement census inherit the same defect and
should be re-measured with it: the reported `MAINS↔SELV` min gap of **5.425 mm** is really
**8.000 mm** (it is K1's pair), and the four residual `DC_BUS↔SELV` below-floor pairs are
attributed to T1/T2 at 7.800 mm.

**No main-branch safety gate is affected.** `scripts/measure_cross_domain_creepage.py` reads
the pad's absolute angle straight from the board file alongside the footprint-rotated
position — correct KiCad semantics — and independently reports 9.100 / 8.000. The defect is
confined to the unmerged `analysis/per-pairing-placer-solve` branch.

---

## 5. Proved vs. inferred

**Proved** (measured, re-runnable, five independent paths):

- CST3015 (T1 and T2) intra-package HV↔SELV copper span = **9.100 mm**; G4A-E (K1) = **8.000 mm**.
- Both are invariant under rigid rotation at 0/90/180/270/37° and under both rotation handedness conventions.
- The sheared composition reproduces 7.800 mm and 5.425 mm exactly, at rotation quadrants 1 and 3 only.
- `Pin.pad_rotation_deg` is footprint-relative; T1's is 0.0 despite a file angle of 90°.
- T2's span (9.100 mm) exceeds its determinate 8.0 mm `DC_BUS↔SELV` requirement.

**Inferred** (follows from the above but not re-executed here):

- That T2 drops out of the `{T1, T2}` UNSAT core on a re-solve. The geometry is proved; the CP-SAT re-solve is not run.
- That correcting `_worst_axis_radius` to the single canonical composition removes the 2.100 mm of spurious conservatism the model carries on these packages.

**Not addressed** (out of scope, unchanged):

- Whether the 20.0 mm `SELV↔TANK` figure is obtainable at all. It is not derived, questioned or altered here.
- `5e53ceaa0`'s separate argument that `tank-out`'s declared working voltage is unsupported by its cited source. Independent of this measurement, and untouched.
- K1's pads 13/14 carry **no PCB copper** (F.Fab only, per the 2026-07-29 correction), so the 8.000 mm figure is a land-pattern geometry constant rather than a real copper crossing. It is reported because it is the figure under dispute and the one `pad_geometry.py`'s docstring pins.
