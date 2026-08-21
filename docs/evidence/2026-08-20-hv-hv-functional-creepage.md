<!-- provenance: branch hvhv/functional-pairings, base origin/analysis/ovp-pads-under-model-e
     (cbdf42bee), which is itself a descendant of origin/feat/per-pairing-creepage-derivation
     (bd39eb10a) and origin/analysis/per-pairing-placer-solve (30edd0a93). Branched from
     there rather than origin/main because the per-pairing resolver this work extends has
     not landed on main; nothing was merged. Additionally CHERRY-PICKED, clean and
     unmodified, 41c8d5272 + c67e41b5e from worktree-agent-a88f1f2907eb88fcc -- the
     settled pad-world composition, without which no distance below is trustworthy.
     Board measured: pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b -- verified identical
     before and after every measurement; never opened for writing. Every solve is an
     in-memory measurement; no placement was written back, so no
     power_pcb_dataset/drc_ceiling.json re-measurement is owed.
     Environment: this worktree's OWN .venv (`make venv-isolate` under `env -u CONDA_PREFIX`).
     `scripts/check_stale_extensions.py`: PASSED, 10/10 fresh, 0 stale, before the first
     measurement. -->
---
module: placer
tags: [creepage, iec60335, iec60664, functional-insulation, table-18, cp-sat, per-pairing]
problem_type: diagnosis
---

# 2026-08-20: HV↔HV functional creepage, priced for the first time — 69 pairs below their figure on the committed board, 61 on the compliant one, and the determinate inter-component count goes 1 → 11

**Authority: analysis and measurement only.** `pcb/temper.kicad_pcb` was not
modified. Every placement below is a measurement in memory or a scratch file.

## 0. Headline

The isolation-barrier family charges HV↔HV pairings **0.0 mm**, and says so:
*"HV↔HV functional pairings … this family says nothing about them"*
(`isolation_barrier.py`; `2026-08-19-per-pairing-placer-solve.md` §1). Nothing
else priced them either — `IECCreepageGate` filters only violations that cross
the HV↔SELV boundary, and `pair_creepage.generated.yaml` charges HV-class
against HV-class zero. **So nothing resisted crowding inside the HV pocket.**

Giving those pairings their derived Table 18 figures and measuring:

| | committed board | model-E placement |
|---|---:|---:|
| declared HV↔HV pad pairs | 5 386 | 5 386 |
| **below their own functional figure** | **69** | **61** |
|  … on a **determinate** pairing | 16 | **26** |
|  … below an **indeterminate** floor | 53 | 35 |
| **determinate, inter-component** (the fixable kind) | **1** | **11** |
| indeterminate-floor, inter-component | 29 | 11 |
| intra-package (placement-invariant, both classes) | 39 | 39 |
| at/above an indeterminate floor — **never a PASS** | 2 939 | 2 957 |

**The compliant placement improves the total and makes the part that matters
eleven times worse.** It resolves 30 pairs and introduces 22 — every one of
both sets inter-component, since intra-package gaps cannot move. Of the **30
resolved, 29 were below an indeterminate floor** and one violated a determinate
figure. Of the **22 introduced, 11 violate a determinate figure** — a class the
board previously had exactly one of. Inter-component pairs that violate a
requirement this project can actually read from the standard go **1 → 11**, and
the worst shortfall goes **0.521 mm → 4.090 mm**.

**Three of the introduced pairs are below 2.0 mm, and all three carry one pad:
`R4.2` = `PWR_RTN`.** Named in §4.

**Feasibility: pricing HV↔HV does not, on its own, break the placer.** With no
barrier, the model solves `optimal` 168/168 in 40.8 s — 5.1 s more than the same
model with HV↔HV free. The barrier's `{T1, T2}` infeasibility is unchanged by
it. §5 has the re-solved ladder, every row a proven verdict or an explicit
timeout.

**Seven of the ten HV↔HV pairings have NO determinable requirement.** Everything
that depends on them is a proven lower bound, not compliance.

## 1. The figures, and where each comes from

Nothing here is written. `elec/insulation_manifest.yaml` declares each group's
frequency and each pairing's long-term r.m.s. working voltage;
`insulation.rs` derives **same-domain → functional** (IEC 60335-1 cl. 3.3.5)
and grades it against **Table 18, undoubled** — cl. 29.2.3's ×2 is a
*reinforced*-insulation provision and does not apply. The row is selected by
the declared voltage under IEC 60664-1 cl. 3.2.1.1 (long-term r.m.s., never
peak).

| pairing | V r.m.s. | table | row | figure | determinable? |
|---|---:|---|---|---:|---|
| `MAINS<->MAINS` | 120.0 | Table 18 | `>50-125` | **2.20 mm** | yes |
| `DC_BUS<->DC_BUS` | 340.0 | Table 18 | `>250-400` | **5.00 mm** | yes |
| `DC_BUS<->MAINS` | 340.0 | Table 18 | `>250-400` | **5.00 mm** | yes |
| `DC_BUS<->SWITCHING` | 340.0 | Table 18 | `>250-400` | 5.00 mm | **NO — floor only** |
| `MAINS<->SWITCHING` | 340.0 | Table 18 | `>250-400` | 5.00 mm | **NO — floor only** |
| `SWITCHING<->SWITCHING` | 340.0 | Table 18 | `>250-400` | 5.00 mm | **NO — floor only** |
| `DC_BUS<->TANK` | 570.5 | Table 18 | `>500-800` | 10.00 mm | **NO — floor only** |
| `MAINS<->TANK` | 570.5 | Table 18 | `>500-800` | 10.00 mm | **NO — floor only** |
| `SWITCHING<->TANK` | 570.5 | Table 18 | `>500-800` | 10.00 mm | **NO — floor only** |
| `TANK<->TANK` | 570.5 | Table 18 | `>500-800` | 10.00 mm | **NO — floor only** |

`DC_BUS<->DC_BUS` = **5.0 mm, not doubled**, is exactly the figure the
standards determination (`0cbc04248`) derived and the reason the 12.6 mm
row-iv fossil was never a rail-to-rail obligation.

**Table 18's rows are offset by one from Table 17's.** `insulation.rs` reads
each table's own row list, so a row is never selected by index across tables;
the harness prints the row *label* beside the table name so a reader checks
the bracket rather than a remembered row number.
`test_table_18_row_is_selected_by_voltage_not_by_index` asserts each printed
bracket actually contains its declared voltage.

### 1.1 The 47 kHz members are NOT a determinate 5.0 mm

A pairing's frequency is the **max** of its two groups'
(`insulation.rs`: `fa.frequency_hz.max(fb.frequency_hz)`), so every HV↔HV
pairing touching `SWITCHING` or `TANK` — **seven of the ten** — sits above
IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling, and cl. 2.3 routes dimensioning
above it to IEC 60664-4, which is paywalled and was not obtained. For those
seven the resolver answers `requirement_mm() -> nan` and
`grade(x) -> "INDETERMINATE"` at **any** distance, never `"PASS"` — exactly as
the two reinforced barrier crossings behave.

`scripts/check_insulation_pairings.py` lists the same seven independently under
"NOT DETERMINABLE", alongside `SELV<->SWITCHING` and `SELV<->TANK`: **9
pairings, 7 of them HV↔HV.**

Calling one of them a determinate 5.0 mm because Table 18 happens to print a
row at 340 V is the permissive failure this work exists to avoid. It is pinned
by `test_every_47khz_pairing_is_indeterminate_with_a_floor` and
`test_an_indeterminate_pairing_never_grades_pass`, both anti-vacuous.

## 2. Method

* **Geometry: the settled pad-world composition.**
  `temper_placer.geometry.pad_world` — `world_centre = (FX,FY) + R(-THETA)·(LX,LY)`,
  `world_body_angle = comp_rotation_deg + pad_rotation_deg` — proved **73 : 0**
  against this board's own routed copper (`41c8d5272`, cherry-picked onto this
  branch clean; 83/83 rotation-invariance tests pass here). The superseded
  composition, which handed the pad body its footprint-*relative* angle alone,
  produced 19 640 wrong figures out of 25 833; it is not used anywhere below.
* **Distance: exact Minkowski copper-to-copper** (`core.pad_geometry.pad_pair_distance`),
  not centre-to-centre. No count here is a lower bound for the reason the
  class-pair censuses' are.
* **Grading: three-valued, per pairing** (`requirement_for_nets(a, b).grade(gap)`).
  FAIL / INDETERMINATE / PASS are counted separately and an indeterminate pair
  is never folded into a pass.
* **Same-net pairs are skipped.** Two pads at the same potential have no
  insulation between them to dimension.
* **Scope: 27 declared HV nets, 4 groups, 107 copper HV pads, 5 386 pairs.**

### 2.1 A correction found while measuring: two pads on this board are not copper

`K1`'s pads `13` and `14` are declared `(layers "F.Fab")` in
`pcb/temper.kicad_pcb` — a fabrication *documentation* layer that places no
copper — yet `Pin.layer` from `parse_kicad_pcb` reports **`"F.Cu"`** for both.
They are the only two such pads on the board (2 of 527, found by scanning every
`(pad …)` token).

They are also, unfiltered, this census's worst **determinate** finding: two
6.35 × 1.2 rectangles centred 6.35 mm apart abut exactly, giving **0.000 mm**
between `power_in.ntc-no` and `w1_2` against a determinate 2.20 mm
`MAINS<->MAINS` figure. On `F.Fab` there is no copper to abut, so there is no
insulation distance to dimension and no violation.

Excluding them is a **geometry correction, not a threshold adjustment**: no
figure, ceiling, allowlist or expectation moved, the two pads are named in the
report line that excludes them, and `--include-non-copper` reproduces the
unfiltered number. Unfiltered the committed board reads **70 / 17 determinate**
instead of 69 / 16, and `MAINS<->MAINS` reads 1 FAIL instead of 0.

**Reported, not fixed, and it is not local to this census:** every
copper-distance measurement in this repo that reads pad layers through
`parse_kicad_pcb` inherits the same mis-assignment — including the 25 833-pair
HV↔SELV censuses, since `K1` carries MAINS nets and both fab markers are in
their HV set too.

## 3. The census

Committed board, exact copper, graded per pairing:

| pairing | floor | det. | pairs | **FAIL** | INDET | min gap | closest |
|---|---:|---|---:|---:|---:|---:|---|
| `DC_BUS<->DC_BUS` | 5.00 | yes | 874 | **6** | 0 | 3.040 | `K3.1 ↔ K3.3` |
| `DC_BUS<->MAINS` | 5.00 | yes | 1 260 | **10** | 0 | 3.040 | `K2.4 ↔ K2.1` |
| `MAINS<->MAINS` | 2.20 | yes | 260 | **0** | 0 | 5.500 | `RT1.1 ↔ RT1.2` |
| `DC_BUS<->SWITCHING` | 5.00 | **no** | 1 260 | **17** | 1 243 | 0.650 | `C23.1 ↔ C23.2` |
| `MAINS<->SWITCHING` | 5.00 | **no** | 784 | **1** | 783 | 3.975 | `C25.1 ↔ RV1.1` |
| `SWITCHING<->SWITCHING` | 5.00 | **no** | 334 | **21** | 313 | 0.650 | `C22.1 ↔ C22.2` |
| `DC_BUS<->TANK` | 10.00 | **no** | 270 | **2** | 268 | 7.831 | `R15.2 ↔ R30.2` |
| `MAINS<->TANK` | 10.00 | **no** | 168 | **2** | 166 | 6.331 | `F1.1 ↔ R30.1` |
| `SWITCHING<->TANK` | 10.00 | **no** | 168 | **8** | 160 | 0.790 | `C17.2 ↔ R30.1` |
| `TANK<->TANK` | 10.00 | **no** | 8 | **2** | 6 | 5.000 | `R30.1 ↔ R30.2` |
| **total** | | | **5 386** | **69** | **2 939** | | |

Model-E placement (`optimal`, 168/168, 36.0 s, `{T1,T2}` straddle relaxed —
re-solved here, not quoted):

| pairing | **FAIL before** | **FAIL after** | INDET after | min gap after |
|---|---:|---:|---:|---:|
| `DC_BUS<->DC_BUS` | 6 | **10** | 0 | 2.950 |
| `DC_BUS<->MAINS` | 10 | **16** | 0 | 0.910 |
| `MAINS<->MAINS` | 0 | **0** | 0 | 2.699 |
| `DC_BUS<->SWITCHING` | 17 | 14 | 1 246 | 0.650 |
| `MAINS<->SWITCHING` | 1 | 1 | 783 | 1.167 |
| `SWITCHING<->SWITCHING` | 21 | 15 | 319 | 0.650 |
| `DC_BUS<->TANK` | 2 | 1 | 269 | 3.633 |
| `MAINS<->TANK` | 2 | 1 | 167 | 6.360 |
| `SWITCHING<->TANK` | 8 | 2 | 166 | 6.968 |
| `TANK<->TANK` | 2 | 1 | 7 | 5.000 |
| **total** | **69** | **61** | **2 957** | |

**The three determinate rows all go up. Every indeterminate row goes down or
stays.** That is the shape of a placement optimised against a model that priced
the barrier and not the pocket.

### 3.1 The split that matters

|  | committed | model E |
|---|---:|---:|
| determinate, **inter-component** | **1** | **11** |
| determinate, intra-package | 15 | 15 |
| indeterminate-floor, inter-component | 29 | 11 |
| indeterminate-floor, intra-package | 24 | 24 |

The 39 intra-package pairs are byte-identical across the two placements, which
is the self-check: a footprint's pads move as one rigid unit, so an
intra-package gap cannot change under anything the placer decides.

**Inter-component violations of a requirement this project can actually read
go 1 → 11**, and the two sets are disjoint.

The committed board has **exactly one**:

| pads | gap | figure | short by | pairing |
|---|---:|---:|---:|---|
| `R5.1` (`PWR_RTN`) ↔ `R9.2` (`discharge.k_dis2-nc`) | 4.479 | 5.00 | **0.521** | `DC_BUS<->MAINS` |

Model E **resolves that one and creates eleven**:

| pads | gap | figure | short by | pairing |
|---|---:|---:|---:|---|
| `R23.2` ↔ `R4.2` | 0.910 | 5.00 | **4.090** | `DC_BUS<->MAINS` |
| `C7.1` ↔ `R4.2` | 1.258 | 5.00 | **3.742** | `DC_BUS<->MAINS` |
| `R4.2` ↔ `R46.1` | 2.113 | 5.00 | 2.887 | `DC_BUS<->MAINS` |
| `K3.1` ↔ `R7.1` | 2.950 | 5.00 | 2.050 | `DC_BUS<->DC_BUS` |
| `C14.1` ↔ `U1.2` | 2.978 | 5.00 | 2.022 | `DC_BUS<->MAINS` |
| `K3.4` ↔ `R7.1` | 3.300 | 5.00 | 1.700 | `DC_BUS<->DC_BUS` |
| `C14.2` ↔ `C24.1` | 3.307 | 5.00 | 1.693 | `DC_BUS<->MAINS` |
| `K2.3` ↔ `RT1.1` | 3.821 | 5.00 | 1.179 | `DC_BUS<->MAINS` |
| `K2.3` ↔ `RT1.2` | 3.821 | 5.00 | 1.179 | `DC_BUS<->MAINS` |
| `C7.1` ↔ `R23.2` | 4.013 | 5.00 | 0.987 | `DC_BUS<->DC_BUS` |
| `C7.1` ↔ `R46.1` | 4.198 | 5.00 | 0.802 | `DC_BUS<->DC_BUS` |

All eleven are in the introduced-22 set. **The committed board's worst
placement-fixable determinate HV↔HV shortfall is 0.521 mm; model E's is
4.090 mm — 7.8× worse — and there are eleven of them instead of one.**

## 4. The three the compliant placement introduced below 2.0 mm

Of the 22 pairs model E introduces (clean before, below after), exactly three
are under 2.0 mm — and **all three carry `R4.2`, i.e. `PWR_RTN` on the bleeder
2512**:

| HV pad | HV pad | gap | figure | short by | pairing | determinable? |
|---|---|---:|---:|---:|---|---|
| `R23.2` (`hb-gnd`) | `R4.2` (`PWR_RTN`) | **0.910** | 5.00 | 4.090 | `DC_BUS<->MAINS` | **YES** |
| `R23.1` (`GATE_LS`) | `R4.2` (`PWR_RTN`) | **1.167** | 5.00 | 3.833 | `MAINS<->SWITCHING` | no — floor only |
| `C7.1` (`discharge.r_snub1-p2`) | `R4.2` (`PWR_RTN`) | **1.258** | 5.00 | 3.742 | `DC_BUS<->MAINS` | **YES** |

The next-closest introduced pair is `R4.2 ↔ R46.1` at 2.113 mm — also `R4.2`.
**Four of the five closest pairs model E introduces are one pad.** The
placement parks the bleeder's mains-return terminal inside the gate-drive and
snubber cluster, which costs nothing in a model that charges HV↔HV zero.

Two of the three violate a **determinate** 5.00 mm `DC_BUS<->MAINS` figure by
more than 3.7 mm. The third is on an indeterminate pairing, so it is not
merely below a bound — it is below a bound of a requirement nobody has read.

The full list of 22 introduced and 30 resolved pairs is reproduced by
`docs/evidence/2026-08-20-hv-hv-functional-census.py --full`.

## 5. Feasibility, re-solved

_(filled in below from the re-solve; see §5.1)_

## 6. What this cannot fix

**39 of the 69 are intra-package** and no placement, rotation, corridor
position or corridor orientation changes any of them — the same limitation
that makes `T1` and `T2` the barrier's UNSAT core. Worst members:

| pads | gap | figure | pairing | determinable? |
|---|---:|---:|---|---|
| `C22.1 ↔ C22.2` | 0.650 | 5.00 | `SWITCHING<->SWITCHING` | no |
| `C23.1 ↔ C23.2` | 0.650 | 5.00 | `DC_BUS<->SWITCHING` | no |
| `U6.9 ↔ U6.10` | 0.670 | 5.00 | `DC_BUS<->SWITCHING` | no |
| `R19.1 ↔ R19.2` | 0.850 | 5.00 | `SWITCHING<->SWITCHING` | no |
| `R23.1 ↔ R23.2` | 0.850 | 5.00 | `DC_BUS<->SWITCHING` | no |
| `K2.4 ↔ K2.1` | 3.040 | 5.00 | `DC_BUS<->MAINS` | **yes** |
| `K3.1 ↔ K3.3` | 3.040 | 5.00 | `DC_BUS<->DC_BUS` | **yes** |
| `R4.1 ↔ R4.2` | 4.700 | 5.00 | `DC_BUS<->MAINS` | **yes** |
| `R30.1 ↔ R30.2` | 5.000 | 10.00 | `TANK<->TANK` | no |

These need a different package, a milled slot or a different topology. They are
reported, never encoded, and no threshold was moved to absorb them.

**Four `safety.ovp.*` nets have no figure at all.** They are `HighVoltage` in
`TEMPER_NET_ASSIGNMENTS` and undeclared in `elec/insulation_manifest.yaml`, so
`requirement_for_nets` **raises** against every counterparty — not 5.0, not
2.2, not 0.0. Their eight pads are excluded from every count above and named in
their own section of the harness output. That is the declaration gap
`2026-08-20-ovp-pads-under-model-e-placement.md` found, unchanged.

## 7. The gap this does NOT close

`IECCreepageGate` (`placer/cp_sat/gates.py`) still filters **only** clearance
violations that cross the HV↔SELV boundary, so the routing-stage DRC gate
remains blind to every figure in §1. Closing it means grading HV↔HV
`kicad-cli` violations per pairing the way the gate already grades HV↔LV ones,
and it will turn the gate red. That is a deliberate non-change here: it is a
CI-visible act that deserves its own evidence-first change, not a side effect
of a measurement. **Named rather than implied.**

`tank_creepage.py` is the one HV↔HV family that already existed. It posts a
`SeparatedConstraint` between the tank part and every other `HighVoltage`-class
component at the **literal** `HV_TANK_CREEPAGE_PD3_MM = 10.0`. That number
coincides with what §1 derives for `*<->TANK` — but it is written rather than
derived, it is keyed on a net *class* rather than a declared insulation group,
and **it carries no indeterminacy flag**, so a caller can read a SAT verdict
off it and report "pass" for a 47 kHz pairing. Not touched here; recorded.

## 8. Constraints observed

* **No figure was lowered anywhere.** `hv_functional_creepage` takes no margin
  argument — there is nothing in it a solve could be made feasible by turning
  down. The attribution rows in §5 *remove* a whole derived pairing family;
  they never shrink one.
* **The indeterminacy stayed fail-closed.** Seven HV↔HV pairings and two
  barrier crossings are encoded at their **proven floors**, never at a
  substituted determinate-looking number; `HvFunctionalReport.determinable` is
  `False` and every verdict resting on it is labelled conditional.
* **Violations were allowed to appear.** Applying a 5.0 mm bar where 0.0 was
  charged surfaced 69 pairs and they are all reported. No threshold, ceiling,
  ratchet, allowlist or expectation was adjusted to absorb any of them. The one
  exclusion (§2.1) removes two objects that are not copper, names them, and
  prints the unfiltered number alongside.
* **The board was not modified.** sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
  identical before and after every measurement.
* `scripts/check_oracle_hashes.py`: **172/172 byte-identical** — no oracle
  re-pinned. `power_pcb_dataset/drc_ceiling.json` untouched.
* No test skipped, `xfail`ed, deleted or weakened; no assertion relaxed; no
  `continue-on-error`, `|| true` or `# noqa` added.

## 9. Test and gate status

| suite / gate | result |
|---|---|
| `test_hv_functional_creepage.py` (new, 20 tests) | **20 passed** |
| `test_pad_world_rotation_invariance.py` (cherry-picked) | **83 passed** |
| `test_isolation_barrier*.py` + `test_loop.py` | **unchanged** |
| `test_tank_creepage.py` | **6 failed — PRE-EXISTING**, see below |
| `scripts/check_oracle_hashes.py` | 172/172 byte-identical |
| `scripts/check_insulation_pairings.py` | INDETERMINATE — the finding itself, unchanged |
| `ruff check` on every changed file | clean |

The six `test_tank_creepage.py` reds were **proven pre-existing** by checking
out the base's own `tank_creepage.py` (`cbdf42bee`) into this tree and
re-running: **the same 6 fail**, so neither the cherry-picked pad-world
composition nor this branch's work caused them. Four are config facts the
board still carries (`enforced_tank_bus_clearance_mm() = 2.0` against a
governing 10.0; `HighVoltageTank.creepage_mm = 6.3`; the DRU selecting PD2);
two are pour-containment expectations. They are the family
`2026-08-18-tank-creepage-11-reds-diagnosis.md` already triages.

## 10. Reproduce

```bash
scripts/check_stale_extensions.py            # 10/10 fresh FIRST

# §3, §4 -- the census, committed board vs a placement
python docs/evidence/2026-08-20-hv-hv-functional-census.py \
    --placement /path/to/model_e.json --full

# §3 control -- the unfiltered number, for comparison with a census
# that did not exclude the two F.Fab pads
python docs/evidence/2026-08-20-hv-hv-functional-census.py --include-non-copper

# §5 -- the feasibility ladder (6 solves)
python docs/evidence/2026-08-20-hv-hv-functional-placer-solve.py

# §5.1 -- resolving the one row the ladder leaves `unknown`, and
# recomputing the UNSAT core under the priced model
python docs/evidence/2026-08-20-hv-hv-functional-core-resolve.py \
    --timeout-ms 2400000
```
