<!-- provenance: commit=55655ea7df30304b1592e312165b270688303ed7 dirty=UNKNOWN -->
     Board measured: pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     (verified unchanged before and after -- Sec 8). kicad-cli 10.0.5,
     --all-track-errors, single-threaded KICAD_CONFIG_HOME pin via
     temper_placer.validation._drc_api._single_threaded_kicad_env, DRU
     regenerated from scripts/generate_kicad_dru.py at this commit.
     ALL DRC runs were against SCRATCH COPIES under /tmp; the tracked board
     was never opened for writing. Analysis and proposal only -- no board
     authorization was held or exercised. -->
---
module: placer
tags: [creepage, tank, pd3, iec60335, drc, analysis-only, test-triage]
problem_type: diagnosis
---

# 2026-08-18: Diagnosing the "11 failing tests" in `test_tank_creepage.py`

**Authority:** analysis and proposal only. `pcb/temper.kicad_pcb` was NOT modified.

## 0. Headline corrections to the briefed premise

Four briefed facts did not survive measurement. Each is corrected below with the
measurement that contradicts it.

| # | Briefed | Measured |
|---|---|---|
| 1 | 11 failing tests, all honest reds about board creepage shortfalls | **7 failing** on `main` in a correctly-provisioned venv. 5 of the apparent extras are an environment artifact (`ModuleNotFoundError: temper_constraints`) |
| 2 | Measured 6.3mm vs 10.0mm required, uniform across the failures | **No test asserts 6.3-vs-10.0 on board geometry.** The real board figures are 5.0000mm and 5.1960mm. 6.3 appears only as the PD2 *constant* |
| 3 | The 11 are honest reds about *real board creepage shortfalls* | **Only 2 of the 7** concern board geometry, and both are *stale pins asserting a shortfall that no longer exists*. 4 are value/SSOT assertions; 1 is a stale state pin |
| 4 | PRs #1081/#1084 enforcement branches are **not** on `main` | Both **are** merged on `main` (`c2b03fb23`, `3231dc3db`). The module docstrings saying otherwise are stale |

The test file's path is `packages/temper-placer/tests/placer/cp_sat/test_tank_creepage.py`,
not `tests/placer/cp_sat/...`.

## 1. The 7 failures, precisely

Run: `.venv/bin/python -m pytest packages/temper-placer/tests/placer/cp_sat/test_tank_creepage.py -p no:randomly` → **7 failed, 20 passed**.

| # | Test | Asserts | Actual | Class |
|---|---|---|---|---|
| 1 | `TestGroupMembership::test_other_hv_refs_excludes_tank_refs` | `{"K2","R12","R19"} <= other_hv_refs` | `R12` absent — its only nets are `DISCHARGE_CTRL` and `discharge.q_dis_drv-g`, both **unassigned** in `TEMPER_NET_ASSIGNMENTS`, so it is not HV-classified at all | **TEST BUG** — wrong ref in the assertion. This is the one PR #1348 fixes; that PR is not yet on `main` |
| 2 | `TestTankBusCopperMetric::test_pour_contained_tank_pads_are_detected` | `C26.2` and `R30.1` lie inside `DC_BUS_RTN` pours | Both are **outside**: C26.2 is **86.408mm** and R30.1 **79.541mm** from the nearest `DC_BUS_RTN` zone outline | **STALE PIN** — geometry improved |
| 3 | `TestTankBusCopperMetric::test_pour_bounded_pairs_violate_pd3` | 2 pour-bounded violations at 2.0mm | **Zero.** All 8 tank↔bus pad gaps are 15.46–96.04mm, every one ≥ PD3 | **STALE PIN** — the shortfall is gone |
| 4 | `TestTankBusEnforcement::test_enforced_netclass_clearance_meets_pd3` | netclass clearance ≥ 10.0mm | 2.0mm | **VALUE SHORTFALL** (see §4 caveat) |
| 5 | `TestTankBusEnforcement::test_enforced_netclass_clearance_meets_pd2` | netclass clearance ≥ 6.3mm | 2.0mm | **VALUE SHORTFALL** (same caveat) |
| 6 | `TestTankBusEnforcement::test_dru_rule_currently_selects_pd2` | `_TANK_POLLUTION_DEGREE == "PD2"` | **`"PD3"`** — `HV_TANK_CREEPAGE_ENFORCED_MM` = 10.0 | **STALE STATE PIN** — the fix landed; the test still pins the defect |
| 7 | `TestTankBusEnforcement::test_ssot_declared_creepage_meets_pd3` | `HighVoltageTank.creepage_mm` ≥ 10.0 | 6.3 (and `HighVoltage` 6.0) | **VALUE SHORTFALL** — real |

**Not one of the 7 is an honest red about a live board creepage shortfall.**
Failures 2 and 3 are the only board-geometry assertions, and both fail because the
board got *better*, not worse.

## 2. The real board shortfalls (which no failing test currently reports)

Live `kicad-cli pcb drc` on a scratch copy, DRU regenerated at this commit.
Harness sanity: `lib_footprint_issues`=13, `lib_footprint_mismatch`=26 —
**not** the 168/0 misconfiguration signature. Total creepage: **106**
(uncapped; the 199/499 caps are not in play).

Rule `HighVoltageTank functional creepage` (`min 10.0mm`) — **exactly 2 violations**:

| pair | actual | required | short by | placement-fixable? |
|---|---:|---:|---:|---|
| `R30` pad 1 (`tank.c_tank1-p2`) ↔ `R30` pad 2 (`tank-out`) | **5.0000mm** | 10.0mm | 5.0000mm | **No** — intra-footprint |
| `R30` pad 1 (`tank.c_tank1-p2`) ↔ `R18` pad 2 (`hb.power_loop.q_high-g`) | **5.1960mm** | 10.0mm | 4.8040mm | **Yes** — §5 |

A third pad pair on the same net pair is masked by kicad-cli's reporting model
(§3): `R30` pad 1 ↔ `T1` pad 1 (`tank-out`) at **8.2547mm**, short by 1.7453mm.

Both figures were reproduced independently by this repo's own
`core.pad_geometry.pad_pair_distance` kernel to 4 decimal places (5.0000 / 5.1960),
so the DRC figure and the geometric model agree exactly on the pairs that matter.

### Measurement regime — stated explicitly

`tank.c_tank1-p2`, `tank-out`, `hb.power_loop.q_high-g`, `+170V_BUS` and
`DC_BUS_RTN` all carry **zero track segments**, and the board has **zero filled
zones** (`filled_polygon` count = 0) despite 151 zone outlines. Every figure above
is therefore **pad-to-pad**, and is a **lower bound**: routing and pour fill can
only introduce shorter copper-to-copper paths, never longer ones. The historical
4.8668mm pad-to-routed-copper violation on this same net pair
(`2026-08-12-tank-creepage-geometry.md` §3) is the precedent.

## 3. kicad-cli reports one creepage violation per NET PAIR, not per pad pair

106 creepage violations span **102 distinct net pairs** (4 pairs appear twice).
kicad-cli reports the worst instance per (net pair, rule). Consequence, confirmed
by experiment (§6): with `R30`'s own pad pair fixed, `R30`↔`T1` at 8.2547mm
**surfaces as a new violation** on the same net pair. A creepage violation *count*
is a count of net pairs, and clearing the reported instance does not clear the pair.

## 4. Functional vs safety creepage — which requirement each pair falls under

The authoritative per-pair table is `packages/temper-placer/configs/pair_creepage.generated.yaml`:

- **Functional (HV↔HV), 10.0mm**: `HighVoltage|HighVoltageTank`,
  `HighVoltageSignal|HighVoltageTank`, `HighVoltageTank|HighVoltageTank`.
- **Reinforced (HV↔LV/SELV), 12.6mm**: `HighVoltageTank|Power`, `|Signal`,
  `Default|`, `Ground|`, `FinePitch|`, etc.

Both §2 violations are **functional**. They are a different requirement from the
12.6mm `MIN_BARRIER_WIDTH_MM` reinforced barrier and must not be conflated.

Separately, 7 violations of `HighVoltageTank to LV` at **12.6mm reinforced** touch
tank-node pads (C27↔U21 ×5, C27↔R71, R30↔R15). These are *safety* creepage, are
**not** what `tank_creepage.py` is about, and are not among the 7 failing tests.

**Working voltages are established, not assumed.** `tank.c_tank1-p2` ↔ bus rails =
570.5 Vrms; `tank.c_tank1-p2` ↔ `tank-out` = **544.6 Vrms**
(`2026-08-12-tank-creepage-geometry.md`:45, `2026-08-13-tank-fault-interruption.md`:26).
Both land in Table 18 band vi (>500–800 V), IIIa/IIIb → 6.3mm PD2 / **10.0mm PD3**.
The 10.0mm figure is therefore correctly applied to both §2 pairs, not over-applied.

### Caveat on failures 4 and 5

`enforced_tank_bus_clearance_mm()` returns a **clearance** (2.0mm), and the test
compares it against a **creepage** requirement (10.0/6.3mm). These are different
physical quantities under IEC 60335-1 (cl. 29.1 vs 29.2) with independent tables.
The creepage requirement for this pair *is* enforced — by the DRU rule, at 10.0mm.
Whether the 2.0mm clearance is itself adequate is a real and separate question
(clearance for 570.5 Vrms is a Table 16 determination), but these two tests as
written do not establish it. They are red for a reason that is **category-confused**,
even though 2.0mm is genuinely low.

## 5. Standards provenance for 10.0mm — obtainable, and doubly sourced

- **IEC 60335-1 Table 18** (functional insulation, cl. 29.2.4) recovered verbatim in
  `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` §3.1. Band
  `>500 and ≤800`, IIIa/IIIb: PD2 **6.3**, PD3 **10.0**.
- **IEC 60335-1 Table 17** (basic insulation) recovered verbatim in
  `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3.3, same band,
  same cells (10.0 at PD3 IIIa/IIIb) — the two tables coincide at and above 500 V,
  so the figure is supported twice. Table 17 additionally carries an external
  Broadcom/IEC 60664-1 cross-check; **Table 18 has no external cross-check.**
- Encoded as a live SSOT lookup, not a literal:
  `scripts/generate_kicad_dru.py` uses `_tdb.creepage_table_lookup(3, "IIIa/IIIb", ">500-800", "18")`
  against `packages/temper-design-bundle/src/safety_value.rs::TABLE_18`.
- **PD3 governs as built** — the PD2 route requires a sealed compartment that does
  not exist (`2026-08-11-pd2-decision-record.md`, `2026-08-15-pd2-pd3-data-driven-decision.md`).

**On the briefed "Table 8 is OCR-garbled" warning:** Table 8 is *Maximum Winding
Temperature* (cl. 11/19.1/19.11), not a creepage table. There is no numbering shift
between 8, 17 and 18. The prohibition is real and correctly recorded
(`docs/HANDOFF-2026-08-17.md`:78) but **does not touch the 10.0mm figure**.

**Not obtainable** (correctly, and stated as such): an external cross-check of
Table 18; IEC 60335-1 Annex L; IEC 60664-4's normative tables (the 44–50 kHz
correction — which could only raise the requirement, never lower it); and a
laminate MPN/CTI that would actually *pin* the material group. IIIa/IIIb is a
conservative assumption, and IEC 60335-1 merges IIIa and IIIb into one column, so
nothing moves unless the laminate is shown to reach group II (CTI > 400).

## 6. Is the enforcement actually wired? Partly — and it is dark by default

`add_tank_creepage_to_model` is **not orphaned**, but it is **unreachable in the
default shipping flow**:

- Its only production call is `_encoder_solve.py:474`, inside `solve_placement`,
  guarded by `if tank_creepage is not None` (`:471`).
- The only site that passes that kwarg is `cli/__init__.py:676`, inside the
  **`--no-loop`** branch (`:562`).
- `--loop` is the **default** (`cli/__init__.py:229-231`) and is what both
  `scripts/run_clean_flow.sh:44-49` and `scripts/run_physics_flow.sh` actually run.
- The loop path's `solver_kwargs` (`_loop_core.py:84-109`) has **no `tank_creepage`
  key**. The same is true of `isolation_barrier` and `heatsink_colocation` — all
  three opt-in safety families are dark under `--loop`.
- There is no CLI flag, config key, env var or YAML entry that can enable it.

For comparison, the briefed claim about `domain_clearance` is **confirmed**: the
real symbol is `generate_domain_clearance_constraints`
(`domain_clearance.py:290`), whose only production call is
`repair_commands.py:247` inside `_domain_constraints`, reached only from
`repair_unplaced` (`:492-498`) behind `--domain-clearance`. It never reaches
`solve_placement()`.

**So the constraint that would have prevented the R30↔R18 shortfall exists, is
sound, and never runs in the default flow.** That is the most consequential finding
here. Note it would *not* have prevented the other two: R30's own pad pair is
intra-footprint (no `SeparatedConstraint` can separate one part's own pads), and
R30↔T1 is below the box-proxy's resolution.

### The box proxy is very loose in this direction

`check_tank_creepage_separation` at 10.0mm rejects **15** of the 180 component
pairs on the committed board. Only **2** of those 15 correspond to a real copper
shortfall. Examples of the proxy's false positives: `C25`×`RV1` box gap 0.400mm but
copper **43.80mm**; `C27`×`U4` box gap 0.400mm but copper **41.40mm**. Enforcing
the box constraint as HARD at 10.0mm would force 15 component relocations to fix 1
real pair (R30↔R18 — the other real pair is intra-footprint and invisible to it).
This is worth knowing before wiring it into `--loop`.

## 7. Placement fixability, costed

All candidates below were built into scratch copies and measured with live
`kicad-cli` DRC. Baseline: total 776, creepage 106, clearance 179,
courtyards_overlap 1.

### 7a. `R30`↔`R18` (5.1960mm) — FIXABLE

`R18` is a 1206 at `(46.14, 115.35, 180°)`. Swept 36 directions × 0.5mm steps for
the minimum displacement reaching 10.0mm, then DRC-verified the survivors:

| candidate | `R18` → | move | creepage | clearance | courtyards | verdict |
|---|---|---:|---:|---:|---:|---|
| baseline | (46.140, 115.350) | — | 106 | 179 | 1 | 2 functional violations |
| a240 | (43.140, 110.154) | 6.0mm | 105 | 179 | **2** | new courtyard overlap |
| a270 | (46.140, 109.350) | 6.0mm | 105 | 178 | **2** | new courtyard overlap |
| a280 | (47.182, 109.441) | 6.0mm | 105 | 178 | 1 | **clean, minimal** |
| a290 | (48.363, 109.242) | 6.5mm | 105 | 177 | 1 | clean |
| **a300** | **(49.640, 109.288)** | **7.0mm** | **104** | **177** | **1** | **best: −2 creepage, −2 clearance** |

Every candidate shows `via_dangling` +1 — a via on `R18`'s (unrouted) net is left
unattached by the move; it resolves on the next route and is not a geometry
regression.

**Recommended: `R18` → (49.640, 109.288), a 7.0mm translation, no rotation.**
Clears the violation and *improves* two other categories.

**Functional caveat the owner must weigh:** `R18` is the high-side IGBT gate
resistor on `hb.power_loop.q_high-g`. Moving it 7mm lengthens the gate loop
(inductance/EMI at a 44–50 kHz switching node). This is the same class of objection
that made `C22` infeasible in `2026-08-17-pd3-creepage-12-reexamination.md` §4.
`physics/gate_drive.py` and `physics/loop_area.py` own that question; this analysis
does not settle it.

### 7b. `R30`'s own pads (5.0000mm) — NOT placement-fixable, and NOT cheaply footprint-fixable

No placement constraint can ever separate one footprint's own pads. `R30` is
`lib:LitzPad_15A`: two 8mm-diameter THT pads at 13mm pitch → 5.0mm edge gap.
Reaching 10.0mm needs ≥18mm pitch. Measured:

| candidate | creepage | Δ | functional violations |
|---|---:|---:|---|
| baseline | 106 | — | 2 (5.0000, 5.1960) |
| `R30` pitch 13→18mm | 113 | **+7** | 2 (5.1960, **8.2547 ← `R30`↔`T1` surfaces**) |
| `R30` pitch 13→18.5mm | 114 | **+8** | 2 (same) |
| `R30` 18.5mm + `R18`→a300 | 113 | **+7** | 1 (8.2547, `R30`↔`T1`) |

**Re-pitching `R30` is a net regression**: it clears one functional violation and
creates seven new creepage violations elsewhere, because pad 2 sweeps 5mm into a
congested neighbourhood. This independently reproduces the historical result — a
widened 26.0×8.0mm `R30` was tried in `2026-08-12-tank-creepage-geometry.md` and
not retained.

Reducing pad diameter instead is infeasible: 3mm pads on a 3mm drill is zero
annular ring. A milled slot cannot be substantiated — IEC 60335-1 Annex L is
paywalled and **not obtainable** (`2026-08-13-hv-creepage-edge-reaching-slot-determination.md`).

**This escalates to mechanical/topology change**, as briefed-for. The
`tank.c_tank1-p2`/`tank-out` pair is the coil's own two terminals at 544.6 Vrms;
the topology places them on one part by construction.

### 7c. `R30`↔`T1` (8.2547mm) — masked, and blocks any complete fix

Not currently reported (§3). It becomes the binding violation the moment `R30`'s
pitch is fixed. `T1` is the current transformer whose primary carries the tank
return — `main.ato:823-824`, *"Tank return passes THROUGH the CT primary."* Its
adjacency to the tank node is topological.

## 8. Board integrity

```
before: 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b  pcb/temper.kicad_pcb
after:  26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b  pcb/temper.kicad_pcb
```

Identical. `git status` clean throughout. Every DRC run used `shutil.copy` into
`/tmp/.../scratchpad/`; the tracked board was never opened for writing.
`pcb/temper.kicad_dru` was regenerated (it is gitignored, `.gitignore:58`) and is
byte-identical to what the generator produces at this commit.

## 9. Recommendations (no board change made or authorized)

1. **Do not "fix" the 7 tests by weakening them.** Five need re-deriving against
   the current board/config; that is a correction of stale expectations, not a
   relaxation. Specifically:
   - #1 → land PR #1348 (drop `R12`; it is not HV-classified).
   - #2, #3 → re-derive: the pour-containment shortfall no longer exists.
   - #6 → invert: pin `_TANK_POLLUTION_DEGREE == "PD3"`. It currently pins the
     defect and fails *because the fix landed*.
   - #4, #5 → re-target onto the enforced **creepage** figure, or re-state
     explicitly as a clearance-adequacy question with its own Table 16 derivation.
   - #7 → keep red. `HighVoltageTank.creepage_mm` = 6.3 vs 10.0 is a genuine SSOT
     shortfall.
2. **Add a test that actually covers the live shortfall.** Nothing in this file
   asserts on the two real functional violations. A test pinning
   `R30`↔`R18` at 5.1960mm and `R30`↔`R30` at 5.0000mm would be an honest red.
3. **Decide on `--loop` wiring.** `tank_creepage`, `isolation_barrier` and
   `heatsink_colocation` are all dark in the default flow. Wiring tank creepage in
   at the box proxy's 10.0mm would force 15 relocations to fix 1 pair (§6) — the
   proxy needs tightening (e.g. pad-level rather than box-level) before that is
   worth doing.
4. **Escalate `R30`.** The 5.0000mm intra-footprint pair and the 8.2547mm
   `R30`↔`T1` pair are not placement problems. They need a coil-terminal decision.

## Files

- This document. No other files changed. `pcb/temper.kicad_pcb` NOT modified (§8).
