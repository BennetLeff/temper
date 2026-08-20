---
title: "Hole-to-hole and hole-to-edge CP-SAT placement constraints, and the measured attribution of the model-E copper regressions"
date: 2026-08-19
branch: agent/hole-edge-placement-constraints
stacked_on: agent/per-pairing-placement-route @ bc3a19b06
board_sha256: 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
status: constraints landed and proven feasible; the regressions they were commissioned to fix are measured to have a different cause
---

# Hole geometry in the placer — and what `hole_clearance +24` / `drill_out_of_range +14` actually were

## 0. Headline

Two things, and the second is the more important one.

1. **The two constraints are implemented, sound, tested, and FEASIBLE.** The
   CP-SAT model genuinely did not constrain drilled holes at all. It now
   constrains inter-component hole-to-hole and hole-to-board-edge. Adding
   both keeps the solve `optimal` at 168/168 in 42.2 s. **The model does not
   become infeasible, so there is no UNSAT core to extract**; the core stays
   `{T1, T2}`, exactly as on the branch below.

2. **They do not fix `hole_clearance` or `drill_out_of_range`, because those
   are not hole-to-hole or drill-to-edge violations and are not
   placement-caused.** Measured, not inferred, by four independent routes.
   The brief's premise, inherited from `bc3a19b06`'s own reported-against-
   interest note, is a **category misreading**:

   | kicad-cli category | what it actually checks (kicad-cli's own text) | placement can cause it? |
   |---|---|---|
   | `drill_out_of_range` | `Hole size out of range (board setup constraints min hole 0.3000 mm; actual 0.2000 mm)` — a hole **diameter** | **No.** Moving a footprint cannot change a drill size. |
   | `hole_clearance` | `Hole clearance violation (rule 'Via hole clearance' clearance 0.2800 mm; actual …)` — hole-to-**copper** | Only via router copper. |
   | `hole_to_hole` | `Drilled hole too close to other hole (rule 'PTH hole to hole' min 0.4995 mm; …)` — the actual hole-to-hole rule | Yes — and it is **0 on every placement measured here**. |

   `hole_to_hole` does not appear in `bc3a19b06`'s delta table at all, which
   is consistent: it was 0 → 0.

**Consequence for the bar.** The success condition (improve connectivity *and*
regress no copper or fabrication category) is **not reached**, and adding
these constraints could not have reached it. §4 gives the honest per-category
table. §5 answers the brief's question 5 with per-item evidence.

---

## 1. Provenance of every figure, and one figure that does not exist

Read from the tree, never invented:

| figure | value | source |
|---|---:|---|
| hole-to-hole | **0.5 mm** | `scripts/generate_kicad_dru.py`'s `(rule "PTH hole to hole") (constraint hole_to_hole (min 0.5mm))`, resolved by generating the DRU in-process |
| hole-to-hole (board setup) | 0.3 mm | `pcb/temper.kicad_pro` `design_settings.rules.min_hole_to_hole` — **looser**; KiCad enforces the stricter, so the placer takes the max |
| hole-to-edge | **0.5 mm** | `pcb/temper.kicad_pro` `design_settings.rules.min_copper_edge_clearance` — confirmed to be the figure kicad-cli checks holes against by its own violation text |
| min through-hole diameter | 0.3 mm | `pcb/temper.kicad_pro` `design_settings.rules.min_through_hole_diameter` — the `drill_out_of_range` threshold |

**No JLCPCB hole-to-hole or hole-to-board-edge figure exists in this
repository.** `docs/hardware/FAB_CAPABILITY.md` and
`docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md` source three hole
rows — 2a annular ring (0.254 mm), 2b minimum drill diameter (0.15 mm), 2c
hole-to-**copper** (0.28/0.35/0.2 mm) — and two edge rows, 5a/5b, both
edge-to-**copper** (0.2/0.4 mm). None of them is hole-to-hole or
hole-to-edge. Per the brief's instruction, that gap is reported rather than
filled: both 0.5 mm figures are this repo's own design values, and
`HoleRequirements.hole_to_hole_fab_sourced` / `.hole_to_edge_fab_sourced` are
both `False` so no caller can mistake them for fab-traceable.

`scripts/generate_kicad_dru.py`'s literal `0.5mm` was lifted to a named
`PTH_HOLE_TO_HOLE_MM = 0.5` so the placer reads the enforced figure instead of
re-typing it. **`generate_dru()`'s output is byte-identical** before and after
(sha256 `095207fb…0305` both ways;
`scripts/tests/test_generate_kicad_dru.py` 35/35 green). No value changed.

### An in-tree inconsistency found on the way, reported not fixed

`pcb/temper.kicad_pro` declares `min_through_hole_diameter: 0.3` mm, but the
router emits vias with a **0.2 mm** drill — the geometry
`docs/hardware/FAB_CAPABILITY.md` §4 records as the 2026-08-13 annular-ring
fix ("now 0.8mm/0.2mm and 1.0mm/0.4mm"). Every `drill_out_of_range` violation
on every board measured here is exactly one of those 0.2 mm vias (§5). The two
in-tree figures disagree; 0.2 mm is comfortably above JLCPCB's sourced 0.15 mm
minimum drill, so the *fab* is not the constraint. **Changing either figure is
explicitly out of scope** (no drill or DRU threshold may be moved to make
something pass), so this is recorded as an open question for the owner.

---

## 2. The encoding

`packages/temper-placer/src/temper_placer/placer/cp_sat/hole_geometry.py`.

For component `c`, over its drilled pads `k` at local offset `(ox_k, oy_k)`
with hole radius `r_k`:

    Ax(c) = max_k ( |ox_k| + r_k )        Ay(c) = max_k ( |oy_k| + r_k )

**Family A — inter-component hole-to-hole.** For any holes `h_i ∈ i`,
`h_j ∈ j`, projecting on X:

    gap = euclid(h_i,h_j) − r_i − r_j
        ≥ |c_ix − c_jx| − (|ox_i| + r_i) − (|ox_j| + r_j)
        ≥ |c_ix − c_jx| − Ax(i) − Ax(j)

so **either** `|Δx| ≥ Ax(i)+Ax(j)+H` **or** `|Δy| ≥ Ay(i)+Ay(j)+H` is
sufficient for every hole pair across the two components. That is the same
Chebyshev disjunction `handlers/separated.py` already uses. An axis projection
lower-bounds the Euclidean distance, so the encoding can only ever
**over**-constrain — it can never admit a placement whose true hole gap is
below `H`.

**Family B — hole-to-board-edge.** Same `Ax`/`Ay` against the outline inset by
the edge figure. A non-rectangular outline is **refused**, not approximated by
its bounding box: that approximation is unsound in the direction that matters
(it would permit holes outside a concave board).

**Rotation is exact, not worst-cased.** Under the model's rotation table
(`rot=0:(lx,ly) rot=1:(ly,−lx) rot=2:(−lx,−ly) rot=3:(−ly,lx)` — the
`isolation_barrier._project_onto_barrier_axis` table, independently
re-verified here against kicad-cli's own reported coordinates, below),
`|gx|` is `|lx|` at even rotations and `|ly|` at odd ones, so `Ax`/`Ay` simply
**swap**, selected by `AddElement` off the same `rot_ref` that drives
`x_size`/`y_size`.

**Intra-footprint hole pairs are reported, never constrained** — no placement
can move a footprint's own pads relative to each other, so posting that
constraint would make the model spuriously infeasible for something placement
does not control (the argument `domain_clearance.py` already makes about
intra-footprint domain straddling). The real board has **0** such violations.

**Cost:** 35 hole-bearing components → 595 pairs + 35 edge constraints. Solve
time 37.8 s → 42.2 s.

### A bug this module shipped with, and the test that now pins it

`Pin.drill` is **not** uniformly a float: SMD pads carry `0.0`, through-hole
pads carry a `DrillDefinition` pyclass (`parse_engine.rs`: "`DrillDefinition`
objects (not floats) flow into `Pin.drill`"). The first draft tested
`float(pin.drill)` inside `try/except TypeError`, which classified **all 94**
of the board's real drilled pads as drill-free and posted **zero**
constraints while reporting success — the exact silent-no-op failure mode
`AGENTS.md` warns about. `TestDrillExtraction` now pins the real board's
94-holes/35-footprints population, so a regression to that behaviour fails
rather than passing vacuously.

### Verification

* **Soundness, real board.** Over all 595 hole-bearing component pairs of the
  committed placement, the bound never over-claims the true Euclidean hole
  gap; tightest observed slack **0.0000 mm** (i.e. exact on the binding pair).
  Also swept over all 16 rotation pairs × 25 offsets on adversarial synthetic
  parts.
* **Geometry validated twice, independently.** A raw-s-expression census
  (`hole_census.py`) and the placer's Rust parser agree that the committed
  placement's minimum inter-component hole gap is **3.9509 mm** — to four
  decimals, through two entirely separate code paths.
* **Rotation convention validated against kicad-cli itself.** U27 `(at 33.1
  47.96 90)`, pad 2 local `(−9.0, 8.89)`: kicad-cli's DRC reports it at
  `(41.99, 56.96)`. The KiCad Y-down transform reproduces that exactly; the
  standard math-CCW transform gives `(24.21, 38.96)`. **My first census used
  the wrong one** and reported a phantom 0.2321 mm C26↔K3 violation; with the
  correct transform the figure is 3.9509 mm and agrees with kicad-cli's
  `hole_to_hole = 0`.
* **Binding on a real `CpSatModel`**, pin-and-solve, each rejection paired
  with a control that isolates the constraint from the component box.
* `packages/temper-placer/tests/placer/cp_sat/test_hole_geometry.py`: **43
  passed**.

---

## 3. The solve verdict — feasible, no UNSAT core

Committed board, seed 42, 600 s budget, per-pairing setbacks MAINS 4.80 /
DC_BUS 8.00 / SWITCHING 8.00 [floor] / TANK 20.00 [floor],
`all_determinable = False`, T1+T2 relaxed exactly as row E.

| row | | status | wall | placed |
|---|---|---|---:|---:|
| E | barrier only (branch row E) | `optimal` | 37.8 s | 168/168 |
| E+H | + inter-component hole-to-hole | `optimal` | 36.6 s | 168/168 |
| E+G | + hole-to-board-edge | `optimal` | 39.3 s | 168/168 |
| **E+HG** | **+ both** | **`optimal`** | **42.2 s** | **168/168** |

**No ablation was needed.** The brief anticipated possible infeasibility; the
honest answer is that both families are satisfiable on this board with large
margin, so there is no core to report. The UNSAT core of the *barrier* is
unchanged at `{T1, T2}`.

**CONDITIONAL**, as on the branch below: the TANK (20.0 mm) and SWITCHING
(8.0 mm) setbacks are **proven floors, not requirements** — both pairings are
47 kHz, above IEC 60664-1's 30 kHz scope and routed by cl. 2.3 to the
paywalled 60664-4. A SAT verdict certifies the floor was cleared; it does not
certify compliance. **T1 is left relaxed and not prejudged**: whether its
`tank-out` pad is a 120 V node or a tank node turns on a bench measurement
nobody has taken.

**On T2 / CST3015.** This branch still computes the 7.800 mm span, so T2
remains in the relaxed set here. `analysis/settle-cst3015-copper-span`
@ `6a240af9b` settles the span at 9.100 mm by rotation-invariance, which would
clear T2's 8.0 mm `DC_BUS<->SELV` figure with 1.1 mm margin and drop it from
the core — but that branch is **not merged here**, and re-deriving its result
was outside this task. Stated, not assumed.

---

## 4. The measurement — placement-only vs routed

All figures in this branch's own (20.0 mm barrier) router configuration, which
is what "stack on `agent/per-pairing-placement-route`" means. Note this is
**not** `bc3a19b06`'s §3 configuration (12.6 mm), so its 251/539 headline is
not the comparison here; the reproduced §4 figures are.

**Baseline reproduces exactly.** Committed placement routed: 758 segments,
52 vias, 37/139 nets, 354 `unconnected_items`. Model-E: 6166 segments,
79/139 nets, 258 `unconnected_items` — `bc3a19b06` §4 to the unit.

### 4a. Placement-only DRC — every routed trace, via and zone stripped

This is the decomposition that settles the attribution question. Copper
stripped with the router's own `strip_existing_copper`, so a "bare" board here
is byte-for-byte what the router starts from. 3 samples each.

| category | committed | model-E | **E+HG** |
|---|---:|---:|---:|
| `creepage` | 255 | 112 | **107** |
| `clearance` | 36 | 37 | 37 |
| `silk_overlap` | **199 †** | 4 | 73 |
| `silk_over_copper` | 42 | 14 | 82 |
| `courtyards_overlap` | 1 | 0 | 0 |
| `silk_edge_clearance` | 1 | 2 | 1 |
| `lib_footprint_mismatch` | 26 | 26 | 26 |
| `lib_footprint_issues` | 13 | 13 | 13 |
| `missing_courtyard` | 5 | 5 | 5 |
| **`hole_clearance`** | **0** | **0** | **0** |
| **`hole_to_hole`** | **0** | **0** | **0** |
| **`drill_out_of_range`** | **0** | **0** | **0** |
| **`copper_edge_clearance`** | **0** | **0** | **0** |
| **`shorting_items`** | **0** | **0** | **0** |
| **`solder_mask_bridge`** | **0** | **0** | **0** |
| **`via_dangling`** | **0** | **0** | **0** |
| total | 578 | 212–213 | 344–345 |

† `silk_overlap` 199 is kicad-cli's `ERROR_LIMIT`, a **saturation floor, not a
count**. Every delta involving it is a bound. It is not quoted as an
improvement anywhere in this document.

**Six categories are identically zero on all three placements.** Placement
causes none of them.

### 4b. Static hole geometry of the placements themselves

| quantity | requirement | committed | model-E | **E+HG** |
|---|---:|---:|---:|---:|
| min inter-component hole-to-hole | ≥ 0.5 mm | 3.9509 | 3.8598 | **5.5791** |
| min hole-edge to board outline | ≥ 0.5 mm | 4.6000 | 1.3500 | **1.0000** |
| drilled pads below min drill 0.3 mm | 0 | 0 | 0 | **0** |
| violating hole pairs | 0 | 0 | 0 | **0** |

**Row E already satisfied both constraints, with 7.7× and 2.7× margin.** It
was never in violation of either. Both families are therefore *non-binding* at
the returned optimum: they change the search (E+HG is a different tie-break of
the same optimum, not a repair of row E), and what they buy is a **guarantee**
where previously there was only luck.

### 4c. Routed DRC, all three placements

| category | committed | model-E | E+HG | E−cmt | EHG−cmt |
|---|---:|---:|---:|---:|---:|
| `clearance` | 71 | 310 | 262 | **+239** | **+191** |
| `creepage` | 245 | 114 | **109** | −131 | **−136** |
| `silk_over_copper` | 42 | 14 | 82 | −28 | +40 |
| `silk_overlap` | **199 †** | 4 | 73 | ≤−195 | ≤−126 |
| `copper_edge_clearance` | 1 | 15 | 39 | +14 | **+38** |
| `via_dangling` | 13 | 41 | 38 | +28 | +25 |
| `shorting_items` | 5 | 58 | 35 | **+53** | **+30** |
| `hole_clearance` | 2 | 60 | 35 | **+58** | **+33** |
| `drill_out_of_range` | 2 | 22 | 15 | **+20** | **+13** |
| `hole_to_hole` | 0 | 2 | 1 | +2 | +1 |
| `track_dangling` | 0 | 3 | 4 | +3 | +4 |
| `solder_mask_bridge` | 5 | 4 | 4 | −1 | −1 |
| `courtyards_overlap` | 1 | 0 | 0 | −1 | −1 |
| `silk_edge_clearance` | 1 | 2 | 1 | +1 | 0 |
| `lib_footprint_*`, `missing_courtyard` | 44 | 44 | 44 | 0 | 0 |
| **total** | **631** | **693** | **742** | +62 | +111 |
| segments / vias | 758 / 52 | 6166 / 194 | 5121 / 195 | | |

### 4d. Connectivity

| metric | committed | model-E | **E+HG** |
|---|---:|---:|---:|
| `unconnected_items` | 354 | 258 | **249** |
| nets fully pad-connected | 37/139 | 79/139 | **79/139** |
| …on the ≥2-pad denominator | 10/112 | 52/112 | **52/112** |
| nets with zero copper and zero zone | 90 | 39 | **38** |
| pads connected | 132/496 | 218/496 | **224/496** |

Connectivity improves and holds; the copper categories still regress. **The
bar is not met.**

---

## 5. Are `clearance +89` and `shorting_items +23` also placement-caused?

**No — and neither are `hole_clearance` or `drill_out_of_range`.** Three
independent lines of evidence, all measurement.

### 5a. They are zero without a router

§4a: `shorting_items`, `hole_clearance`, `drill_out_of_range`,
`copper_edge_clearance`, `hole_to_hole` and `solder_mask_bridge` are **0 on
all three bare placements**. `clearance` moves 36 → 37 → 37 — i.e. **+1**, not
+239. Whatever produces the routed +239 is not in the placement.

### 5b. kicad-cli names the geometry, and it is router copper

Every violation classified by the item descriptions kicad-cli itself emits
(`Pad …` = placement geometry; `Track`/`Via`/`Blind via`/`Zone`/`Polygon` =
copper emitted by this route):

| category | routed model-E | ROUTER-ONLY | pad-involved |
|---|---:|---:|---:|
| `drill_out_of_range` | 22 | **22 (100 %)** | 0 |
| `copper_edge_clearance` | 15 | **15 (100 %)** | 0 |
| `via_dangling` | 41 | **41 (100 %)** | 0 |
| `hole_to_hole` | 2 | **2 (100 %)** | 0 |
| `hole_clearance` | 60 | 50 | 8 † |
| `shorting_items` | 58 | 52 | 4 |
| `clearance` | 310 | 207 | 102 |

† and every one of those 8 names a **via** as the other item — i.e. the hole
is always router-emitted. `hole_clearance` is hole-to-**copper**; not one
violation on any board is a footprint pad's hole against another footprint
pad's hole.

Verbatim examples:

```
drill_out_of_range: Hole size out of range (board setup constraints
    min hole 0.3000 mm; actual 0.2000 mm)
  * Via [RTD_CS_N] on F.Cu - B.Cu
hole_clearance: Hole clearance violation (rule 'Via hole clearance'
    clearance 0.2800 mm; actual 0.0000 mm)
  * Track [safety.thermal-line] on In4.Cu, length 48.3000 mm
  * Via [s1] on F.Cu - B.Cu
hole_to_hole: Drilled hole too close to other hole
    (rule 'PTH hole to hole' min 0.4995 mm; actual 0.4350 mm)
  * Blind via [refin_n] on In4.Cu - B.Cu
  * Via [refin_n] on F.Cu - B.Cu
```

### 5c. The `drill_out_of_range` mechanism is exact and predicted

`drill_out_of_range` = **the number of router-emitted vias with a 0.2 mm
drill**, which is below `pcb/temper.kicad_pro`'s `min_through_hole_diameter =
0.3 mm`. The static census predicts kicad-cli's count exactly on every board:

| board | 0.2 mm vias (census) | kicad-cli `drill_out_of_range` |
|---|---:|---:|
| bare committed / bare model-E / bare E+HG | 0 / 0 / 0 | 0 / 0 / 0 |
| routed committed | 2 | **2** |
| routed model-E | 22 | **22** |
| routed E+HG | 15 | **15** |

Same for `hole_to_hole` (0 / 2 / 1 predicted, 0 / 2 / 1 reported). All 94
footprint pad drills are 0.7–3.0 mm on every board and are **unchanged by
placement**. No placement constraint can move this number; only the router's
via-template choice can.

### 5d. Verdict

* `hole_clearance`, `drill_out_of_range`, `copper_edge_clearance`,
  `hole_to_hole`, `via_dangling`, `track_dangling`: **router artifacts**,
  0 % attributable to placement.
* `shorting_items`: **90 % router-only** (52/58); the residual 4 are
  pad-vs-router-copper, i.e. the router laying copper onto a foreign-net pad —
  which is `fixed_copper.py`'s domain, not hole geometry's.
* `clearance`: **67 % router-only** (207/310); the 102 pad-involved are all
  pad-vs-router-**copper**, and the placement-only count is 36 → 37. So the
  volume hypothesis in `bc3a19b06` §5c is **confirmed and quantified**: the
  model-E route lays 8.1× the segments and 3.7× the vias into the space the
  keepout-union compaction opened up, and the clearance count tracks the
  copper, not the footprints.

**The correction to `bc3a19b06`'s note.** Its statement that
"`hole_clearance` +24 and `drill_out_of_range` +14 are PLACEMENT-CAUSED and a
genuine defect … the CP-SAT model does not constrain hole-to-hole spacing or
drill-to-edge" is wrong on both halves: the *premise* about the model was
correct (it really did not constrain them — that gap is now closed), but the
*attribution* was not, and the two categories named are not the two
constraints named. The placement was never in violation of either.

**What this leaves as the real open defect** is a router problem, in three
parts and in priority order: (1) it emits 0.2 mm-drill vias against a 0.3 mm
board-setup minimum; (2) it places blind vias and through vias of the *same
net* closer than 0.5 mm hole-to-hole and stacks copper within 0.28 mm of via
holes; (3) it routes copper past the 0.5 mm board-edge clearance.

---

## 6. Constraints observed

* **`pcb/temper.kicad_pcb` was never modified.** sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
  before and after every step. Every candidate board was written to a scratch
  path outside the repo.
* **No requirement was lowered.** No clearance, creepage, copper-weight,
  loop-area, ampacity, annular-ring, drill or DRU threshold changed. The
  `PTH_HOLE_TO_HOLE_MM` refactor is byte-identical in `generate_dru()`'s
  output. `hole_geometry.py` authors no figure and **raises** on a
  caller-supplied value that would relax either (tested both ways).
* The two indeterminate pairings stayed fail-closed at their proven floors of
  20.0 mm and 8.0 mm; `all_determinable` is `False` and every dependent
  verdict above is labelled CONDITIONAL. T1 was left relaxed and not
  prejudged.
* No test skipped, xfailed, deleted or relaxed; no ratchet raised; no
  allowlist broadened; no oracle re-pinned; `drc_ceiling.json` untouched; no
  `git stash`. The 6 pre-existing `test_tank_creepage.py` failures were
  confirmed identical at `HEAD` before and after these changes (they are the
  documented "expected red" enforcement-shortfall group).
* Saturated counters: `silk_overlap` 199 = `ERROR_LIMIT`, marked † wherever it
  appears and never quoted as an improvement. `unconnected_items` was checked
  against its former 499 cap — all values here (249–382) are well below it.

---

## 7. Reproduction

```bash
env -u CONDA_PREFIX make venv-isolate
.venv/bin/python -c "import temper_design_bundle_python as t; \
    assert hasattr(t,'resolve_insulation_declaration')"

# 1. solve: rows E / E+H / E+G / E+HG  (~2.5 min)
.venv/bin/python docs/evidence/2026-08-19-hole-geometry-solve.py \
    --emit /tmp/placement_EHG.json --ablate

# 2. write to a scratch board (never pcb/temper.kicad_pcb)
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-apply-placement.py \
    --placement /tmp/placement_EHG.json --output /tmp/board_EHG.kicad_pcb

# 3. route (~195 s each)
.venv/bin/python scripts/route_board.py --pcb pcb/temper.kicad_pcb \
    --output /tmp/routed_committed.kicad_pcb
.venv/bin/python scripts/route_board.py --pcb /tmp/board_EHG.kicad_pcb \
    --output /tmp/routed_EHG.kicad_pcb

# 4. the attribution: strip all copper, then DRC the bare placements
.venv/bin/python docs/evidence/2026-08-19-hole-geometry-strip-copper.py \
    --board /tmp/board_EHG.kicad_pcb --output /tmp/bare_EHG.kicad_pcb
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-measure-board.py \
    --pcb /tmp/bare_EHG.kicad_pcb --repo "$PWD" --label bare_EHG \
    --samples 3 --scratch /tmp/drcscratch

# 5. static hole census + per-item attribution
.venv/bin/python docs/evidence/2026-08-19-hole-geometry-census.py \
    --board /tmp/routed_EHG.kicad_pcb --repo "$PWD"
.venv/bin/python docs/evidence/2026-08-19-hole-geometry-drc-attribution.py \
    --pcb /tmp/routed_EHG.kicad_pcb --repo "$PWD" --scratch /tmp/drcscratch

# 6. the encoding's own tests
.venv/bin/python -m pytest \
    packages/temper-placer/tests/placer/cp_sat/test_hole_geometry.py -q
```

Digests from this session (sha256). These are the **20.0 mm** router
configuration, so they are NOT `bc3a19b06` §3's 12.6 mm digests; the
metric values reproduce its §4 table exactly (758/6166 segments, 37/79 of
139 nets, 354/258 `unconnected_items`).

| board | sha256 |
|---|---|
| `pcb/temper.kicad_pcb` (unmodified, verified before and after) | `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` |
| E+HG placement, pre-route | `ee26d2421b7c821e55a1bdd01a20263bf5ac81d430dfe5c3f07cbdec70b15d28` |
| routed committed placement | `2b0d36102d0f1a9849a2675481165be2e02cf193c7f2d7b9c82e75232d0f8a79` |
| routed model-E | `128d5c3202c583ffd9ce8183c364e354a80dadfcd08957d3405bd8accdda5dfb` |
| **routed E+HG** | `af2996ff1d94790ecad2c9d3fc788df735e4f38992c3cbafeb7c39aeb69d2069` |
