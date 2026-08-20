<!-- provenance: branch analysis/per-pairing-placer-solve, base origin/main eb5022510,
     = merge of origin/feat/per-pairing-creepage-derivation (bd39eb10a) and
     origin/fix/wire-placer-constraints (7db8375cc), both merged clean.
     Board measured: pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b -- verified
     identical before and after every measurement; never opened for writing. Every
     solve below is an in-memory measurement. No placement was written back, so no
     power_pcb_dataset/drc_ceiling.json re-measurement is owed.
     Environment: this worktree's OWN .venv (`make venv-isolate` under
     `env -u CONDA_PREFIX`). `scripts/check_stale_extensions.py` run before the first
     measurement: PASSED, 10/10 fresh, 0 stale; and `resolve_insulation_declaration`
     verified present on the temper_design_bundle_python surface before any run
     (the check_stale_extensions.py timestamp comparison alone does not prove it).
     Machine: 24 cores, load average 1.2-3.1 across the run. -->
---
module: placer
tags: [cp-sat, creepage, iec60335, iec60664, isolation-barrier, unsat-core, per-pairing]
problem_type: diagnosis
---

# 2026-08-19: the placer solved at the PER-PAIRING creepage figures — everything places except two intra-package shortfalls, T1 and T2

**Authority: analysis and measurement only.** `pcb/temper.kicad_pcb` was not
modified. The placement produced below is a measurement written to a scratch
file, not a candidate for the board.

## 0. Headline

`MIN_BARRIER_WIDTH_MM = 12.6` — one scalar for every HV↔SELV crossing — was
replaced on `feat/per-pairing-creepage-derivation` by a requirement derived per
*pairing* of declared net groups. This is the first solve ever run against those
figures. The placer was wired to encode them, and it was asked.

| what was asked | verdict | time |
|---|---|---:|
| inter-component separation only (DRU-resolved netclass + tank creepage) | **`optimal`**, 168/168 | 35.4 s |
| the same, plus the per-pairing isolation barrier, all 8 isolators | **`infeasible`** | 24.3 s |
| the same, with **T1 alone** relaxed | **`infeasible`** | 24.5 s |
| the same, with **T1 and T2** relaxed | **`optimal`**, 168/168 | 36.8 s |

**The UNSAT core is `{T1, T2}` — two independent singleton cores, both
intra-package, neither fixable by any placement. It shrank from five members
under the 12.6 mm scalar to two under the derived figures.**

Three headline consequences:

1. **C6, K1 and U6 were never real failures.** They were failing a scalar charged
   to the wrong pairing. At their own figures — 4.8, 4.8 and 8.0 mm — all three
   place, and the solver proves it.
2. **T1 is not the only remaining obstacle.** Relaxing T1 alone leaves the model
   `infeasible`. T2 is short by 0.200 mm against a *fully determinate* 8.0 mm
   `DC_BUS<->SELV` figure, which is a much cheaper problem than T1's ≥12.2 mm
   shortfall against a figure that does not exist.
3. **Everything else places, and places compliantly.** In the achieved placement
   every HV pad on the board except T1's and T2's clears its own pairing's
   requirement; `MAINS<->SELV` and `SELV<->SWITCHING` go to **zero** below-floor
   pairs, and 467 of the 503 known-violating pad pairs are resolved.

**Everything below that depends on `SELV<->TANK` or `SELV<->SWITCHING` is
CONDITIONAL.** Those two pairings have no determinable requirement (47 kHz, above
IEC 60664-1's 30 kHz ceiling; IEC 60664-4 not obtained); their 20.0 and 8.0 mm
figures are **proven lower bounds** and clearing them is not compliance.

## 1. What "per-pairing" means in the placer

The scalar model encoded **one corridor of one width**. The per-pairing model
keeps **one barrier line** — there is one physical barrier — and gives each HV
group its own **setback** from it, with the whole SELV domain flush against it:

| HV group | setback | governing pairing | determinable? |
|---|---:|---|---|
| `MAINS` | **4.8 mm** | `MAINS<->SELV` | yes |
| `DC_BUS` | **8.0 mm** | `DC_BUS<->SELV` | yes |
| `SWITCHING` | **8.0 mm** | `SELV<->SWITCHING` | **NO — proven floor only** |
| `TANK` | **20.0 mm** | `SELV<->TANK` | **NO — proven floor only** |

Every figure is read from `elec/insulation_manifest.yaml` through
`insulation.rs`; none is written in the placer. `per_pairing=True` **refuses** a
caller-supplied `corridor_width_mm` — a caller-chosen width is exactly the
scalar this replaces, and accepting one would let a solve be made feasible by
lowering a requirement.

**Soundness.** For an HV pad in group *G* and any SELV pad, the two constraints
force separation along the barrier axis of at least `setback(G) + 0 =
floor(G↔SELV)`. Axis-projected separation lower-bounds Euclidean separation,
which lower-bounds the true creepage path. The model can only over-constrain.

**Strict generalisation.** With all setbacks equal to *W* and no pad-level
rotation, the encoding reduces exactly to the scalar path's
`achievable_gap_mm >= corridor_width_mm`. Pinned by
`test_per_pairing_reduces_to_the_scalar_model_when_setbacks_are_equal` over 4
widths × 2 barrier axes.

**What it still does not encode.** HV↔HV functional pairings (`DC_BUS<->TANK`,
floor 10.0 mm, and friends) sit entirely on the barrier's HV side; this family
says nothing about them. They are the netclass family's job. Named rather than
implied.

## 2. A defect found on the way: the barrier's pad model was optimistic

`compute_pad_groups` builds each `Pad` from width/height/shape and **never reads
`Pin.pad_rotation_deg`** — the pad's own `(at x y ANGLE)`. On a footprint whose
pads are individually rotated, that omission makes the model report *more*
separation than the copper has. Measured against
`core.pad_geometry.pad_pair_distance` (the exact Minkowski kernel the REQ-SAFE-01
validator and `check_isolation_keepout.py` both use):

| ref | footprint | barrier model *before the fix* | exact copper | over-report |
|---|---|---:|---:|---:|
| K1 | `Relay_SPST_Omron-G4A-E` | 8.000 mm | **5.425 mm** | **2.575 mm** |
| T1 | `CST3015` | 9.100 mm | **7.800 mm** | **1.300 mm** |
| T2 | `CST3015` | 9.100 mm | **7.800 mm** | **1.300 mm** |
| C6, K2, K3, PS1, U6 | — | (agreed exactly) | — | 0.000 |

The 8.000 / 9.100 figures in the middle column are the ones
`fix/wire-placer-constraints`' §4c table also reports, computed the same way.
They are package *maxima* under a pad model that drops the pad angle, not the
copper.

A 1.3 mm over-report is not cosmetic: it is exactly enough to turn T2's real
0.2 mm shortfall against the 8.0 mm `DC_BUS<->SELV` figure into a model **PASS**,
i.e. to certify a part its copper does not support.

**Fixed in the strict direction, without guessing a convention.** Composing a
footprint rotation with a pad angle is genuinely ambiguous here — a pad angle in
a `.kicad_pcb` is already absolute (the convention `check_pad_orientation.py`
polices), but this model is choosing a *new* footprint rotation and whether the
writer re-composes is a property of the writer. So `_worst_axis_radius` takes the
**largest** axis radius over all three candidates (`model_rot`, `pad_rot`,
`model_rot + pad_rot`) rather than picking one. It is ≥ each, so the encoded gap
is ≤ the gap under whichever convention holds: it can only over-constrain. It is
deliberately *not* the unconditional worst case over all angles (`(w+h)/2`),
which would be conservative past usefulness.

The consequence is that the model now reports T1 and T2 at **7.000 mm** where the
exact kernel says 7.800 mm — conservative by 0.8 mm. Both numbers are reported
below; neither changes either part's verdict.

**The scalar path was left untouched.** It is covered by a Rust differential and
by `Pad` equality assertions; `_pairing_hv_items` is a parallel reader over the
same `comp.pins`. All 65 pre-existing barrier/loop tests still pass unchanged.

## 3. Per-isolator geometry at the per-pairing figures

Rotation-searched, placement-invariant (rotating a footprint rotates every pad
*and* every pad position together, so intra-package pad distances cannot be
changed by the placer):

| ref | binding HV net | group | required | model gap | exact gap | at 20.0 scalar | per-pairing |
|---|---|---|---:|---:|---:|---|---|
| C6 | `PWR_RTN` | MAINS | 4.80 | 8.000 | 8.000 | FAIL | **PASS** |
| K1 | `power_in.ntc-no` | MAINS | 4.80 | 5.425 | 5.425 | FAIL | **PASS** |
| K2 | `discharge.k_dis1-nc` | DC_BUS | 8.00 | 12.760 | 12.760 | FAIL | **PASS** |
| K3 | `discharge.k_dis2-nc` | DC_BUS | 8.00 | 12.760 | 12.760 | FAIL | **PASS** |
| PS1 | `+170V_BUS` | DC_BUS | 8.00 | 35.500 | 35.500 | PASS | **PASS** |
| U6 | `hb-gnd` | DC_BUS | 8.00 | 8.100 | 8.100 | FAIL | **PASS** (0.100 margin) |
| **T2** | `hb-gnd` | DC_BUS | 8.00 | **7.000** | **7.800** | FAIL | **FAIL** (short 0.2 exact) |
| **T1** | `tank-out` | TANK | **20.00** | **7.000** | **7.800** | FAIL | **FAIL** (short ≥12.2) |

**Six of eight now clear their own requirement.** Under the 12.6 mm scalar,
`fix/wire-placer-constraints` found five failing packages (C6, K1, T1, T2, U6);
under the derived figures **three of those five — C6, K1, U6 — were never real
failures at all.** They were failing a figure charged to the wrong pairing.

## 4. The solve, and the UNSAT core

Real board, 168 components, 164 × 234 mm. `solve_placement` with DRU-resolved
netclass figures + tank creepage at `DEFAULT_TANK_CREEPAGE_MM`, seed 42, 600 s
budget (240 s for ablation rows), no cProfile, load average 1.2–3.1.

| # | model | verdict | time | placed |
|---|---|---|---:|---:|
| **A** | inter-component only (netclass + tank creepage), **no barrier** | **`optimal`** | 35.4 s | 168/168 |
| **B** | A + per-pairing barrier, **all 8 isolators enforced** | **`infeasible`** | 24.3 s | — |
| **D** | B with **T1 alone relaxed** | **`infeasible`** | 24.5 s | — |
| **E** | B with **T1 and T2 relaxed** | **`optimal`** | 36.8 s | 168/168 |

### 4a. Ablation — one isolator enforced, all others relaxed

`solver.SufficientAssumptionsForInfeasibility()` returns **empty** here (each
isolator's rotation pin is a plain `Add`, so the infeasibility does not depend on
the assumption literals), so the core was recovered by ablation using the
module's own `relax_isolator_straddle` exemption.

| enforced isolator | verdict | time |
|---|---|---:|
| C6 | `optimal` | 38.6 s |
| K1 | `optimal` | 43.7 s |
| K2 | `optimal` | 37.1 s |
| K3 | `optimal` | 34.5 s |
| PS1 | `optimal` | 32.4 s |
| **T1** | **`infeasible`** | 25.6 s |
| **T2** | **`infeasible`** | 25.2 s |
| U6 | `optimal` | 35.4 s |
| **relax exactly {T1, T2}** | **`optimal`** | 36.8 s |

**The core is `{isolator_straddle_T1, isolator_straddle_T2}` — two independent
singleton cores.** Each is sufficient alone; relaxing exactly those two restores
feasibility, so they are also jointly necessary. **Every row above is a proven
verdict — no row timed out — so the core is complete, not a lower bound.**

### 4b. The sentence the brief asked for

**T1 is not the only remaining obstacle. It is the first of two.**

Relaxing T1 alone leaves the model `infeasible` (row D). The board becomes
placeable only when T2 is relaxed as well. Under the 12.6 mm scalar the core had
**five** members {C6, K1, T1, T2, U6}; at the derived per-pairing figures it has
**two** {T1, T2}. Three of the five — C6, K1, U6 — were artefacts of charging a
mains crossing and two bus crossings the tank's figure.

### 4c. Cause, per core member — both intra-package, neither fixable by placement

| ref | binding pair | pairing | required | exact copper | short by | cause |
|---|---|---|---:|---:|---:|---|
| **T1** | `tank-out` (pad 1) ↔ `gnd` (pad 4) | `SELV<->TANK` | **≥20.0**, NOT DETERMINABLE | 7.800 mm | **≥12.200 mm** | **INTRA-PACKAGE** |
| **T2** | `hb-gnd` (pad 1) ↔ `gnd` (pad 4) | `DC_BUS<->SELV` | 8.0 mm | 7.800 mm | **0.200 mm** | **INTRA-PACKAGE** |

Both are the same `CST3015` current-transformer footprint. Rotating a footprint
rotates every pad *and* every pad position together, so the distance between two
pads of one part is invariant under everything the placer can decide. **No
placement, rotation, corridor position or corridor orientation fixes either.**
They need a different package or a different topology.

The two are *not* the same severity and should not be reported as one problem:

* **T2 is short by 0.200 mm against a fully determinate 8.0 mm figure.** It is a
  near miss on a real requirement. A `CST3015` variant with 0.2 mm more creepage,
  or moving `hb-gnd` off that winding, closes it.
* **T1 is short by at least 12.200 mm against a figure that does not exist.**
  `SELV<->TANK` runs at 47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz scope
  ceiling; cl. 2.3 routes dimensioning above it to IEC 60664-4, which is
  paywalled and was not obtained. 20.0 mm is the **proven lower bound** from the
  ≤30 kHz tables. Even a part that cleared 20.0 mm would not be *compliant* —
  it would be un-disproven. T1 cannot be closed by procurement alone.

## 5. Compliance of the achieved placement

Measured on the `optimal` placement from row E (T1 and T2 relaxed), against the
committed board measured in the same process — so the "before" column is
reproduced, not quoted.

### 5a. The 503 pad pairs

Same method as `2026-08-19-per-pairing-pad-census-before-after.py`: net→class via
`netclass_rules.yaml`, `pin_world_position`, centre-to-centre,
`PairCreepageTable.required`. That script reports **503** violating pad pairs over
107 nets on the committed board; this harness **reproduces 503 / 107 exactly**
before reporting the after.

| | pad pairs | nets |
|---|---:|---:|
| committed board | **503** | 107 |
| solved placement | **132** | 48 |

* **467 of the 503 are resolved** — 92.8% of the before-set.
* 90 are introduced (clean before, violating after).
* Net change **−371**.

Per class pair:

| class pair | before | after |
|---|---:|---:|
| `Default ↔ HighVoltage` | 223 | 86 |
| `HighVoltage ↔ Power` | 208 | 39 |
| `FinePitch ↔ HighVoltage` | 37 | **0** |
| `Default ↔ HighVoltageTank` | 12 | **0** |
| `HighVoltageTank ↔ Power` | 10 | **0** |
| `Default ↔ HighVoltageIsolated` | 6 | 2 |
| `Default ↔ HighVoltageSignal` | 4 | 5 |
| `HighVoltageIsolated ↔ Power` | 2 | **0** |
| `FinePitch ↔ HighVoltageTank` | 1 | **0** |

**125 of the 132 residuals are in the two `HighVoltage` rows, and that is the
net-class reduction, not a per-pairing requirement.** `TEMPER_NET_ASSIGNMENTS`
puts `tank-out` in the `HighVoltage` class alongside `PWR_RTN`, `+170V_BUS`,
`DC_BUS_RTN`, `hb-gnd` and `SW_NODE`, so a KiCad DRU rule for that class must
carry the worst member's 20.0 mm — the casualty
`2026-08-19-per-pairing-creepage-implementation.md` §3.1 flags and hands to
`fix/netclass-tables-reconcile`. Census 1 also counts intra-package pad pairs,
which the placer's netclass family skips by construction (`a == b`).

**Centre-to-centre is an upper bound on the real copper gap, so every count here
is a lower bound on the real violation count** — the caveat the original
measurement states, carried forward unchanged.

### 5b. The exact per-pairing census — the measurement without that caveat

All 109 HV pads × 237 SELV pads = 25 833 pairs at exact Minkowski copper-to-copper
distance (`pad_pair_distance`), each graded by its **own** pairing, three-valued.
Reproduces the committed board's **36** below-floor pairs exactly (1/3/4/28 split)
before reporting the after.

| pairing | floor | determinable | pairs | FAIL before | **FAIL after** | min gap after |
|---|---:|---|---:|---:|---:|---:|
| `MAINS<->SELV` | 4.80 | yes | 7 110 | 3 | **0** | 5.425 |
| `SELV<->SWITCHING` | 8.00 | **no** | 6 636 | 4 | **0** | 8.100 |
| `DC_BUS<->SELV` | 8.00 | yes | 10 665 | 1 | 4 | 6.000 |
| `SELV<->TANK` | 20.00 | **no** | 1 422 | 28 | 4 | 3.005 |
| **total** | | | 25 833 | **36** | **8** | |

**`MAINS<->SELV` and `SELV<->SWITCHING` go to zero.** The mains crossing is fully
compliant at its derived requirement, with 0.625 mm of margin. The switch-node
crossing clears its proven floor by 0.100 mm — but it is `SELV<->SWITCHING`, so
**that is not a pass** and every one of those 6 636 pairs is reported
INDETERMINATE.

**All 8 residuals carry T1 or T2 on the HV side. There is not one residual
attributable to any other part:**

| pairing | HV pad | SELV pad | gap | floor | short | cause |
|---|---|---|---:|---:|---:|---|
| `DC_BUS<->SELV` | T2.1 | T2.4 | 7.800 | 8.00 | 0.200 | **INTRA-PACKAGE** |
| `DC_BUS<->SELV` | T2.2 | T2.3 | 7.800 | 8.00 | 0.200 | **INTRA-PACKAGE** |
| `DC_BUS<->SELV` | T2.2 | R48.2 | 7.897 | 8.00 | 0.103 | inter-component |
| `DC_BUS<->SELV` | T2.2 | T1.4 | 6.000 | 8.00 | 2.000 | inter-component |
| `SELV<->TANK` | T1.1 | T1.3 | 12.572 | 20.00 | 7.428 | **INTRA-PACKAGE** |
| `SELV<->TANK` | T1.1 | T1.4 | 7.800 | 20.00 | 12.200 | **INTRA-PACKAGE** |
| `SELV<->TANK` | T1.1 | R48.2 | 3.005 | 20.00 | 16.995 | inter-component |
| `SELV<->TANK` | T1.1 | T2.3 | 17.200 | 20.00 | 2.800 | inter-component |

The four inter-component ones are an artefact of the relaxation itself: T1's and
T2's straddle constraints were switched off for row E, so their pads were free to
land anywhere, and they landed near each other and near `R48`. They are not
evidence about any other component's placement.

**So the compliance statement is:** at the derived per-pairing figures, the placer
produces a placement in which **every HV pad on the board except T1's and T2's
clears its own pairing's requirement**, and both exceptions are intra-package
geometry.

### 5c. What did not improve, and why it cannot

`uncertifiable` (FAIL + INDETERMINATE) is **8 062 before and 8 062 after**. That is
not a failure of the placement. 8 058 of the 25 833 pairs belong to the two
pairings that have **no determinable requirement at all**; no arrangement of
copper can certify a requirement nobody has read. That number moves when
IEC 60664-4 (or the UL/CSA 6th Ed. >30 kHz creepage text) is obtained, and not
before.

## 6. Constraints observed

* **No requirement was lowered anywhere.** `per_pairing=True` derives every
  setback from `elec/insulation_manifest.yaml` and raises `ValueError` on a
  caller-supplied `corridor_width_mm`. Pinned by
  `test_per_pairing_refuses_a_caller_supplied_corridor_width`.
* **The two indeterminate pairings stayed fail-closed.** `SELV<->TANK` (20.0) and
  `SELV<->SWITCHING` (8.0) were encoded at their **proven floors**, never at a
  substituted determinate-looking number; `BarrierSetbacks.determinable` carries
  `False` for both; `IsolationBarrierReport.determinable` is `False`; and every
  result above that depends on them is labelled conditional. Pinned by
  `test_indeterminacy_propagates_and_is_not_a_number`.
* **The board was not modified.** sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
  identical before and after every measurement. The solved placement went to a
  scratch file outside the repo.
* **The one model change was in the strict direction** (§2), and it is the only
  reason T2 entered the core *in the model* — the exact copper kernel puts T2
  short of its 8.0 mm figure regardless of which model is used.

## 7. Test and gate status

| suite / gate | result |
|---|---|
| `test_isolation_barrier.py` + `test_isolation_barrier_rust_differential.py` + `test_loop.py` | **65 passed** (unchanged; the scalar path was not touched) |
| `test_isolation_barrier_per_pairing.py` (new, 21 tests) | **21 passed** |
| `scripts/check_oracle_hashes.py` | **172/172 byte-identical to their pins — no oracle re-pinned** |
| `scripts/check_insulation_pairings.py` | **INDETERMINATE** — the finding itself, unchanged from the input branch |
| `ruff check` on every changed file | clean |

No test was skipped, `xfail`ed, deleted or weakened. No assertion was relaxed. No
ratchet ceiling was raised. No allowlist was broadened. No `continue-on-error`,
`|| true`, `# type: ignore` or `# noqa` was added.
`clearance_oracle/clearance.py:244` still carries the old 12.6 figure and was
deliberately left untouched.

## 8. Reproduce

```bash
scripts/check_stale_extensions.py     # must report 10/10 fresh FIRST

# §3 -- per-isolator geometry at the derived setbacks (read-only, sub-second)
python docs/evidence/2026-08-19-per-pairing-isolator-feasibility.py

# §4 -- the solve and the UNSAT core (12 solves, ~8 min)
python docs/evidence/2026-08-19-per-pairing-placer-solve.py \
    --timeout-ms 600000 --ablation-timeout-ms 240000 --emit /tmp/placement.json

# §5a/§5b -- compliance of that placement, both censuses
python docs/evidence/2026-08-19-per-pairing-placement-compliance.py \
    --placement /tmp/placement.json

# §2/§5b -- residual attribution + the barrier-model/exact-kernel cross-check
python docs/evidence/2026-08-19-per-pairing-residual-attribution.py \
    --placement /tmp/placement.json
```

## 9. What this leaves open

1. **T2 is a 0.200 mm package problem against a real requirement.** The cheapest
   real fix available on this board.
2. **T1 is a ≥12.200 mm package problem against a requirement that does not
   exist.** Obtaining IEC 60664-4 is a prerequisite to even knowing what T1 needs.
3. **The `HighVoltage` net class carries 20.0 mm because `tank-out` is in it.**
   That is 125 of the 132 residual class-pair violations in §5a, and it is a
   net-class re-partition owned by `fix/netclass-tables-reconcile`.
4. **The barrier's pad model still differs from the exact kernel** (§2). It is now
   conservative rather than optimistic, which is the safe direction, but the two
   should be reconciled onto one geometry — the **scalar** path is still
   optimistic by up to 2.6 mm on this board's real packages.
5. **The barrier encodes no HV↔HV functional pairing** (§1). Those live on one
   side of the barrier and are the netclass family's job.
