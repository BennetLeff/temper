<!-- provenance: commit=30edd0a93cd4843b16bcc361c53fb02727511231 dirty=false
     branch analysis/enumerate-the-five, base origin/analysis/per-pairing-placer-solve
     (30edd0a93) rather than origin/main, because reproducing model E needs the per-pairing
     barrier model, which has not landed on main. Nothing was merged.
     Board measured: pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b -- verified identical
     before and after every measurement; never opened for write. The row-E solve and the
     board it was applied to went to scratch paths outside the repo.
     Environment: this worktree's OWN .venv (`make venv-isolate` under `env -u CONDA_PREFIX`).
     `scripts/check_stale_extensions.py`: PASSED, 10/10 fresh, 0 stale, before the first
     measurement. Add-only: no existing file is modified. -->
---
module: placer
tags: [creepage, iec60335, iec60664, isolation-barrier, per-pairing, residual]
problem_type: diagnosis
---

# 2026-08-20: the five — every HV↔SELV pad pair still below its own figure under the compliant placement, enumerated

**Authority: analysis and measurement only.** `pcb/temper.kicad_pcb` was not
modified. The placement below is a measurement written to a scratch file, not a
candidate for the board.

## 0. Headline

Grading every HV↔SELV pad pair against **its own per-pairing figure** under the
canonical pad-world composition gives **35 → 5**. That count had been reached
twice before (`cbdf42bee`, `d01134515`); this is a third, independent route, and
it is the first time the five are named.

| # | HV pad | SELV pad | nets | pairing | figure | measured | short by | kind |
|---:|---|---|---|---|---:|---:|---:|---|
| 1 | `T1.1` | `R48.2` | `tank-out` ↔ `safety.ovp.comp-inp` | `SELV<->TANK` | **20.00 [FLOOR ONLY]** | **1.9778** | **18.0222** | inter-component |
| 2 | `T1.1` | `T1.4` | `tank-out` ↔ `gnd` | `SELV<->TANK` | **20.00 [FLOOR ONLY]** | **9.1000** | **10.9000** | **INTRA-PACKAGE** |
| 3 | `T1.1` | `T1.3` | `tank-out` ↔ `I_SENSE` | `SELV<->TANK` | **20.00 [FLOOR ONLY]** | **12.4933** | **7.5067** | **INTRA-PACKAGE** |
| 4 | `T2.2` | `T1.4` | `DC_BUS_RTN` ↔ `gnd` | `DC_BUS<->SELV` | **8.00** | **4.7643** | **3.2357** | inter-component |
| 5 | `T1.1` | `T2.3` | `tank-out` ↔ `s1` | `SELV<->TANK` | **20.00 [FLOOR ONLY]** | **18.0429** | **1.9571** | inter-component |

**Exactly one of the five — #4 — is a violation of a determinable requirement.**
The other four are below a **proven floor** on a pairing that has no determinable
requirement at all (47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling;
cl. 2.3 routes dimensioning above it to the unobtained IEC 60664-4). For those
four, "below the floor" is the strongest true statement available, and had they
been *above* it they still would not be compliant.

**Every one of the five carries `T1` or `T2`.** No other component on the board
contributes a residual.

What the parts are, from the board's own `Sheetpath` properties: `T1` is
`ct_sense.ct` and `T2` is `safety.ocp2.ct`, both `temper:CST3015` current
transformers; `R48` is `safety.ovp.r_div_top3`, the last top resistor of the OVP
divider chain, whose pad 2 (`safety.ovp.comp-inp`) is declared SELV while its
pad 1 (`safety.ovp.r_div_top2-p2`) is in neither domain (§8).

## 1. The figures, executed rather than quoted

`barrier_setbacks()` run in-process off this branch, against
`elec/insulation_manifest.yaml` through `insulation.rs`:

```
DC_BUS         8.0000  determinable=True   governing=DC_BUS<->SELV
MAINS          4.8000  determinable=True   governing=MAINS<->SELV
SWITCHING      8.0000  determinable=False  governing=SELV<->SWITCHING
TANK          20.0000  determinable=False  governing=SELV<->TANK
all_determinable = False   widest = 20.0
```

`ENFORCED_POLLUTION_DEGREE = 3`. Every pair below is graded by
`insulation_coordination.requirement_for_nets(net_a, net_b)`, three-valued; no
millimetre figure is written anywhere in the harness.

## 2. The measurement, re-derived rather than inherited

The pad-world composition is re-implemented in the harness straight from the
convention statement, reading the `.kicad_pcb` bytes through `kiutils` — nothing
depends on this repo's parser or on any previously published number:

```
world_centre     = (FX, FY) + R(-THETA) . (LX, LY)
world_body_angle = the pad's own (at .. .. ANGLE), which is ABSOLUTE
```

**`R(-THETA)` was decided again, here, from the board's own routed copper.**
KiCad anchors a track on a pad centre, so both candidate centres were computed
for every pad of every footprint placed at 90 or 270 (the angles at which the
matrices differ) and matched against same-net segment endpoints and via centres:

```
R(-theta) matched where R(+theta) did not : 73
R(+theta) matched where R(-theta) did not :  0
both matched: 1   neither matched: 54
```

73 : 0, reproducing `41c8d5272`'s result independently. All 527 pads and all 168
footprints sit at a multiple of 90°, so `pad_geometry`'s documented body-angle
handedness question cannot affect any figure here.

Distance is exact Minkowski copper-to-copper (`pad_pair_distance`), not
centre-to-centre. Census scope is `elec/domain_manifest.yaml`'s **109 HV pads ×
237 SELV pads = 25 833 pairs**, both before and after.

## 3. The committed board: 35

| pairing | figure | determinable | pairs | below | closest pair |
|---|---:|---|---:|---:|---:|
| `MAINS<->SELV` | 4.80 | yes | 7 110 | **3** | 4.0500 `K1.14 <-> J1.1` |
| `DC_BUS<->SELV` | 8.00 | yes | 10 665 | **1** | 7.1253 `U1.1 <-> C6.2` |
| `SELV<->SWITCHING` | 8.00 | **no** | 6 636 | **4** | 3.5781 `C22.1 <-> R26.2` |
| `SELV<->TANK` | 20.00 | **no** | 1 422 | **27** | 8.8500 `R30.2 <-> D2.1` |
| **total** | | | **25 833** | **35** | |

The four **determinable** shortfalls on the committed board, worst first — this
is the complete list of pairs on this board that are *proven* non-compliant
against a requirement that exists:

| HV pad | SELV pad | nets | pairing | figure | measured | short by |
|---|---|---|---|---:|---:|---:|
| `U1.1` | `C6.2` | `+170V_BUS` ↔ `gnd` | `DC_BUS<->SELV` | 8.00 | 7.1253 | **0.8747** |
| `K1.14` | `J1.1` | `w1_2` ↔ `rtd_force_p` | `MAINS<->SELV` | 4.80 | 4.0500 | **0.7500** |
| `K1.14` | `J1.2` | `w1_2` ↔ `rtd_sense_p` | `MAINS<->SELV` | 4.80 | 4.1831 | **0.6169** |
| `U1.2` | `C6.2` | `power_in.ntc-no` ↔ `gnd` | `MAINS<->SELV` | 4.80 | 4.7652 | **0.0348** |

The remaining 31 are below proven floors on the two indeterminate pairings.

## 4. `K1.14 <-> J1.1` and `K1.14 <-> J1.2` — confirmed, refined, and not among the five

Both figures **reproduce exactly**: `K1.14 <-> J1.1` = **4.0500 mm**,
`K1.14 <-> J1.2` = **4.1831 mm**, both `MAINS<->SELV` against a determinable
**4.80 mm**, short by 0.7500 and 0.6169 mm. `w1_2` is a CMC line-side winding
tap (MAINS); `rtd_force_p` / `rtd_sense_p` are the RTD sensor connector's SELV
pins. This is a mains-to-sensor-connector crossing, and it is real.

**They were never affected by the convention correction.** `K1` and `J1` are both
placed at quadrant 0, where `R(-θ)` and `R(+θ)` are the same matrix; the harness
computes both and they agree to the digit. That is *why* they were already below
12.6 mm and never appeared in the "newly below" set.

**The claim needs one refinement.** They are the two worst `MAINS<->SELV`
shortfalls on this board, and `K1.14 <-> J1.1` at 4.0500 mm is the **smallest
HV↔SELV gap on the board on any determinable pairing**. But the single worst
*determinate barrier* shortfall is `U1.1 <-> C6.2`, `DC_BUS<->SELV`, short by
**0.8747 mm** — larger than either. "The mains barrier's worst determinate
shortfalls" is true only if `MAINS<->SELV` is read strictly; across both
determinable barrier-crossing pairings, `U1.1 <-> C6.2` is worse.

**They are not among the five, and what distinguishes them is that nothing in
their geometry is fixed.** Both are pure inter-component pairs between two freely
placeable parts, and `K1`'s straddle constraint is *enforced* in row E — the
barrier holds `K1`'s MAINS copper a full 4.8 mm back from the SELV side. Under
model E they land at **41.6391 mm** and **44.2260 mm**. Every one of the five, by
contrast, carries `T1` or `T2` — the two parts whose constraints were switched
off, and, for #2 and #3, `T1`'s own package.

## 5. Model E, re-solved and re-applied

Rows B and D were re-run so row E is *shown* to be the strictest satisfiable
model rather than assumed to be:

| row | model | verdict | time |
|---|---|---|---:|
| B | per-pairing barrier, all 8 isolators enforced | **`infeasible`** | 25.1 s |
| D | B with **T1 alone** relaxed | **`infeasible`** | 25.0 s |
| **E** | B with **T1 and T2** relaxed | **`optimal`**, 168/168 | 37.4 s |

seed 42, 600 s budget, setbacks as §1. Applied to a scratch board through the
production write contract: **168 updated / 0 skipped, 0 warnings**, round-trip
oracle **PASS** (168 components / 521 pads), `check_board_containment.py`
**PASS** (168 footprints / 527 pads inside Edge.Cuts).

Two independent soundness checks on the applied board:

* **1 753 intra-package pad pairs, 0 drift.** An intra-package distance is a
  rigid-body invariant; any drift under re-placement would prove the composition
  or the writer wrong. Worst drift 0.0000 mm.
* **All five figures reproduce from the solve JSON without opening the written
  board at all** — recomposed by hand from the committed board's own local pad
  offsets and the solver's positions/rotations. 1.9778 / 9.1000 / 12.4933 /
  4.7643 / 18.0429, to the digit.

| pairing | figure | determinable | pairs | below | closest pair |
|---|---:|---|---:|---:|---:|
| `MAINS<->SELV` | 4.80 | yes | 7 110 | **0** | 8.0000 `C6.1 <-> C6.2` |
| `DC_BUS<->SELV` | 8.00 | yes | 10 665 | **1** | 4.7643 `T2.2 <-> T1.4` |
| `SELV<->SWITCHING` | 8.00 | **no** | 6 636 | **0** | 8.1000 `U6.14 <-> U6.3` |
| `SELV<->TANK` | 20.00 | **no** | 1 422 | **4** | 1.9778 `T1.1 <-> R48.2` |
| **total** | | | **25 833** | **5** | |

All 35 committed offenders except #2 and #3 clear their figure under model E,
by margins of 9.1 to 194 mm. Three of the five (#1, #4, #5) were clear on the
committed board (101.47, 149.39 and 164.60 mm) and are **introduced** by the
placement.

## 6. Fixability, per residual

### 6a. `T1.1 <-> T1.4` and `T1.1 <-> T1.3` — intra-package, and no placement helps

Both are pads of one `temper:CST3015` current transformer. Rotating a footprint
carries every pad *and* every pad position through the same rigid motion, so the
distance between two pads of one part is invariant under everything the placer
can decide — position, rotation, corridor position, corridor orientation. **This
is proved, not argued: the 1 753-pair drift check above returns 0.**

Per-isolator worst intra-package HV↔SELV span, canonical composition, exact
kernel — this is the whole "no placement helps" class on this board:

| ref | footprint | pairing | figure | worst span | verdict |
|---|---|---|---:|---:|---|
| C6 | `C_Disc_D12.5mm_W5.0mm_P10.00mm` | `MAINS<->SELV` | 4.80 | 8.0000 | clears |
| K1 | `temper:Relay_SPST_Omron-G4A-E` | `MAINS<->SELV` | 4.80 | 8.0000 | clears |
| K2 | `temper:Relay_SPDT_Schrack-RT314012` | `DC_BUS<->SELV` | 8.00 | 12.7600 | clears |
| K3 | `temper:Relay_SPDT_Schrack-RT314012` | `DC_BUS<->SELV` | 8.00 | 12.7600 | clears |
| PS1 | `Converter_ACDC_MeanWell_IRM-10-xx_THT` | `DC_BUS<->SELV` | 8.00 | 35.5211 | clears |
| **T1** | `temper:CST3015` | `SELV<->TANK` | **20.00 [floor]** | **9.1000** | **SHORT 10.9000** |
| **T2** | `temper:CST3015` | `DC_BUS<->SELV` | 8.00 | **9.1000** | **clears by 1.1000** |
| U6 | `lib:SOIC16W_Isolated` | `DC_BUS<->SELV` | 8.00 | 8.1000 | clears (0.1000) |

**`T1` is the only intra-package shortfall on this board.** It needs a different
package or a different topology; procurement of a wider `CST3015` variant is not
even sufficient, because 20.0 mm is a floor and a part that cleared it would be
*un-disproven*, not compliant. Closing `T1` requires IEC 60664-4 first.

**This is not a table defect, and that has been checked rather than assumed.**
The certified-component exemption evidence on the unmerged branch
`evidence/component-certification-creepage-exemption` (`582035aee`, path
deliberately not cited here because it does not exist on this branch or on
`main`) establishes from two independent accredited-lab CB reports that
IEC 60335-1 cl. 24.1's
component-standard substitution for creepage is scoped to **functional
insulation** only, and this barrier is **reinforced**; and separately that the
`CST3015-100ED` carries **no agency recognition at all**. So charging a
board-level creepage figure across this transformer's terminals is what the
standard requires, not an artefact — unlike the 20.0 mm charged across a 3.2 mm
1206 body at `R48`/`R53` (`cbdf42bee` §"a table defect, not a placement defect"),
where the two nodes are separated by protective impedance rather than insulation.

### 6b. `T1.1 <-> R48.2`, `T2.2 <-> T1.4`, `T1.1 <-> T2.3` — artefacts of the relaxation

All three are inter-component, all three were clear on the committed board, and
all three exist **because row E switched `T1`'s and `T2`'s straddle constraints
off**. With nothing holding them to a side, both parts were free to land anywhere;
they landed beside each other and beside `R48`. They are evidence about the
relaxation, not about any other component's placement. Under a model in which
those two parts are placeable at all, the placer resolves them the same way it
resolved the other 30 — they are the placer's problem, and a cheap one.

### 6c. A finding that undercuts `T2`'s membership in the UNSAT core

`T2`'s real intra-package span is **9.1000 mm against a determinable 8.00 mm** —
it **clears, by 1.1000 mm** (§6a). The published "T2 is short by 0.200 mm"
(`2026-08-19-per-pairing-placer-solve.md` §4c) does not survive the convention
correction: 7.800 mm was computed under the superseded composition, and the
barrier model's own figure of 7.000 mm comes from `_worst_axis_radius`, which
takes the **max** half-extent over three candidate pad orientations rather than
the one the convention now settles. That conservatism is the safe direction for a
solve, but it is why row B and row D come back `infeasible` and why `T2` had to be
relaxed at all.

**Consequence, stated as a bound and not as a result:** the placer's `{T1, T2}`
UNSAT core is `{T1}` in copper, and `T2`'s relaxation is what produced residuals
#4 and #5 and let `T1` drift beside `R48` for #1. Routing the barrier model onto
the canonical composition would be a *code* change and was deliberately not made
here, so **no re-solve under a corrected model has been run and none is claimed.**
What is measured is that the copper clears; what is not measured is what the
placer would do if told so.

## 7. The complete residual after the compliant placement

| class | count | what it needs |
|---|---:|---|
| below a **determinable** requirement | **1** (`T2.2 <-> T1.4`, short 3.2357 mm) | placement — and it exists only because `T2` was relaxed on a model figure its copper contradicts (§6c) |
| below a **proven floor**, no determinable requirement, **intra-package** | **2** (`T1.1<->T1.4`, `T1.1<->T1.3`) | a different package or topology for `T1`, **and** IEC 60664-4 before any part can be called compliant |
| below a **proven floor**, no determinable requirement, inter-component | **2** (`T1.1<->R48.2`, `T1.1<->T2.3`) | placement, once `T1`/`T2` are placeable |
| **not demonstrably compliant at any distance** | **8 059** of 25 833 | IEC 60664-4, or the UL/CSA 6th Ed. > 30 kHz creepage text. Nothing about copper moves this. |

The last row is the honest headline. 8 058 of the 25 833 pairs belong to
`SELV<->SWITCHING` or `SELV<->TANK`; those two pairings have **no determinable
requirement**, so no arrangement of copper can certify them. Adding the one
determinable failure gives 8 059 pairs that model E does not certify — against
8 062 on the committed board. **The placement resolves 34 of 35 below-figure
pairs and moves the uncertifiable count by three.**

`MAINS<->SELV` goes to **zero below-figure pairs**, with the closest crossing at
8.0000 mm against 4.80 — 3.2 mm of margin. That is the one clean statement
available: **the mains crossing is fully compliant at its derived requirement
under model E**, and `K1.14 <-> J1.1` / `K1.14 <-> J1.2`, the committed board's
worst mains shortfalls, are among the pairs it resolves.

## 8. Scope this measurement does not cover

* **77 of the board's 139 pad-carrying nets (177 pads) are in neither domain of
  `elec/domain_manifest.yaml`**, and the census skips them silently. 27 nets are
  declared HV and 35 SELV. `d01134515` bounds the hazard inside those 77 to
  exactly 4 `HighVoltage` nets / 8 pads — the OVP divider mid-chain taps — and
  the root cause is at the domain level, not the insulation level.
* **HV↔HV functional pairings are outside this family entirely.** They sit on one
  side of the barrier and are the netclass family's job. `cbdf42bee` measures
  that model E makes three of them *worse*.
* **Routed copper, vias and zones are not measured.** This is a pad-to-pad
  census; the board carries 151 zones and zero `filled_polygon`.
* **No DRC was run** on the scratch board, and no ceiling was re-measured,
  because no placement was written back.

## 9. Reproduce

```bash
scripts/check_stale_extensions.py                      # must report 10/10 fresh FIRST

python docs/evidence/2026-08-20-five-residual-solve-and-apply.py \
    --emit /tmp/rowE.json --out /tmp/model_e.kicad_pcb          # ~90 s, 3 solves

python docs/evidence/2026-08-20-five-residual-census.py \
    --model-e-board /tmp/model_e.kicad_pcb \
    --probe K1.14/J1.1 --probe K1.14/J1.2 --probe T1.1/T1.4 --probe T2.1/T2.4

python docs/evidence/2026-08-20-five-residual-convention-and-packages.py
```

## 10. Constraints observed

`pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
identical before and after every measurement, by every script, and asserted in
each one; the board is the writer's template and never its output. No clearance,
creepage, copper-weight, loop-area, ampacity or DRU threshold was touched. No
ratchet raised, allowlist broadened, ceiling re-baselined or oracle re-pinned. No
test skipped, `xfail`ed, deleted or weakened. Add-only — no existing file is
modified. `ruff check` clean on all three new scripts. `git stash` not used.
Nothing was merged.

**CONDITIONAL.** Four of the five residuals, and every `SELV<->SWITCHING` and
`SELV<->TANK` verdict above, rest on a **proven lower bound, not a requirement**.
Clearing a floor is not compliance, and a pair above its floor is not counted
compliant anywhere in this document.
