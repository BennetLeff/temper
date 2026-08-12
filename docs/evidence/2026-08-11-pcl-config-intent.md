# PCL config intent resolution: is `temper_induction_cooker.yaml` stale, aspirational, or both?

<!-- provenance: commit=4a327d920de8daf4cf55ef875fbbec9cacda00e9 dirty=false -->

**Date:** 2026-08-11
**Scope:** Research only. No edits to `temper_induction_cooker.yaml`, the board,
or the reference manifest. Answers the question PR #1026 and #1030 raised but
deliberately did not answer: *why* does none of the 21 PCL constraints have a
safe mechanical fix — is the config stale, aspirational, or mixed?

## Lead: H3 — mixed, and the two halves are not the same kind of mixed

**The zone/board-dimension *numbers* are STALE (H1).** Git history proves the
config's `board_size`/zone bounds were **genuinely correct** for the real,
contemporaneous board as recently as 2026-07-11, and were never touched again
while the board grew underneath them.

**The *engineering intent* behind most component-adjacency and safety-zone
constraints is STILL VALID (H2-shaped) — but the current board's placement was
never produced by trying to satisfy it.** The production placement pipeline
solves against a completely different, auto-generated constraint set, and the
one CI test that actually exercises this PCL config end-to-end runs it against
a frozen fixture board that still matches the config's stale assumptions — so
nothing in CI could ever have caught the drift.

**Net effect:** the owner's instinct ("rewrite the constraints to match the
board") is right for raw coordinate numbers and wrong, dangerously so, as a
blanket policy — applied to the safety-zone constraints it would launder a real
placement defect (HV bus capacitors sitting in zone geometry labelled
`MCU_ZONE`) into a passing check. See the per-constraint table below; nothing
in this config has an edit landed against it in this PR.

---

## Part 1: the evidence timeline (H1 vs H2, resolved by git history)

### 1.1 The config's only four edits, ever

```
65134cfd  2025-12-19  feat(pcl): add pre-built constraint sets for induction cooker
478dbbf1  2025-12-22  fix: resolve correlation analysis bugs and run initial analysis
454f71d9  2026-07-11  fix(placer): repair placement→route seam — board now routes 100%
fe607215  2026-07-11  fix: U3 FinePitch netclass calibration + U4 DRC footprint library table config
```

Four commits across 8 months. The zone geometry has been touched exactly
twice: created (2025-12-19), reshaped from `polygon` to `bounds` format
(2025-12-22), and rewritten to its current form (2026-07-11). **Nothing has
touched it in the 31 days since**, while the board changed 30+ times.

### 1.2 At creation, the config did not match the board — but the board then changed to match it

- **2025-12-19** (`65134cfd`): config created with `board_size: "120mm x 80mm"`,
  L/R split zones (`HV_ZONE` x∈[0,60], `MCU_ZONE` x∈[70,120]).
- **2025-12-18** (`69ee25d7`, one day earlier): the actual board (`pcb/temper.kicad_pcb`)
  already had a `100 × 150mm` Edge.Cuts rectangle with 33 components — **the
  config's stated board size never matched any board that ever existed.** It
  reads as a hand-authored PCL library template (the same commit adds three
  other generic templates: `half_bridge_base.yaml`, `safety_isolation.yaml`,
  `thermal_management.yaml`), not a measurement of the real board.
- **2026-07-11** (`454f71d9`, "repair placement→route seam"): rewrites
  `board_size` to `"100mm x 150mm"` and the zones to bottom(MCU)/mid(barrier)/top(HV)
  bounds — **exactly today's committed content.** The commit message states
  the reason directly: *"config used (x,y,w,h) on a phantom 120x80 board;
  encoder + other configs use (x_min,y_min,x_max,y_max) on the real 100x150
  board."* Checked directly: `pcb/temper.kicad_pcb` **at that commit** was
  still the original 33-component, 100×150mm board (unchanged since
  2025-12-18/2026-01, confirmed via `git show 8916a153:pcb/temper.kicad_pcb`,
  the board's state immediately prior). The commit's own claim of "places
  optimally (33/33), routes 100% (24/24)" is a real, verifiable CP-SAT run
  against that real, contemporaneous board. **This is the one point in this
  config's history where its zone geometry was true.**

### 1.3 The board grew four days later; the config was never told

- **2026-07-15** (`a1e93e8b`, `068cf9dc`, "production board skeleton"): a
  wholesale resync to a real atopile-generated netlist/BOM. Component count
  jumps from 33 to 169 (confirmed: `git show a1e93e8b:pcb/temper.kicad_pcb`
  is the first commit with 169 `"Reference"` properties). Every symbolic
  reference designator the config uses (`J_AC_IN`, `J_COIL`, `J_DEBUG`, `Q1`,
  `Q2`, `U_MCU`, `C_BUS1`, ...) **had been the literal, real board reference
  designators up through this point** — confirmed directly:
  `git show 8916a153:pcb/temper.kicad_pcb | grep Reference` (the last
  pre-resync board state) lists `J_AC_IN`, `J_COIL`, `J_DEBUG`, `J_NTC`,
  `J_USB`, `Q1`, `Q2`, `U_MCU`, `C_BUS1`, `C_BUS2`, `C_BOOT`, `U_GATE`,
  `U_BUCK`, `U_LDO_3V3`, `U_LDO_5V`, `U_CT`, `R_BURDEN`, `C_MCU_1..4`,
  `C_VCC`, `D1`, `D2` verbatim. The 2026-07-15 resync replaced every one of
  these symbolic names with numbered designators (`U1`..`U27`, `C1`..`C40`,
  ...) as part of adopting a real BOM. **The config's component names are not
  invented or aspirational — they are a real board's reference designators
  from a wholesale renumbering the config was never updated to follow.** This
  is the textbook H1 shape.
- The Edge.Cuts outline itself stayed a **stale placeholder** through this
  growth: `docs/METHODOLOGY.md` §7 ("the reference failure") documents that
  the outline remained the original `100 × 150mm` rectangle at the origin
  while footprints spanned `x 31.5–145.9, y 30.7–240.4mm` — **113 of 149
  footprints (76%) physically outside the declared outline**, undetected for
  ~4 weeks because no metric checked outline containment.
- **2026-07-25** (`c6eb12a8`, "real Edge.Cuts outline"): the outline is
  corrected to `(20,20)-(172,254)` = `152 × 234mm`, derived from true pad
  extents + margin. The config's zones, still `[0,0,100,70]` /
  `[0,70,100,80]` / `[0,80,100,150]`, are now provably off-board — not merely
  undersized, but starting 20mm outside the real origin corner.

**This settles H1 vs H2 for the zone/board-dimension numbers unambiguously:
STALE.** The config tracked a real board faithfully as of 2026-07-11; the
board was resynced and its outline corrected over the following two weeks;
the config was never touched again.

### 1.4 Why nothing in CI ever caught this

Two independent, compounding blind spots:

1. **The one test that runs this config against a board runs it against a
   frozen fixture that still matches the config's stale assumptions.**
   `test_golden_board_drc_regression`
   (`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`)
   loads `PCL_CONFIG = .../temper_induction_cooker.yaml` but solves against
   `power_pcb_dataset/corpus/temper/temper.kicad_pcb` — **not**
   `pcb/temper.kicad_pcb`. Directly verified: the corpus fixture is still
   **33 components, `(gr_rect (start 0 0) (end 100 150))`** — assembled
   2026-06-22 (`6db890fb`, "assemble placer regression corpus") and never
   resynced since. This is the *exact* board the config's zones describe.
   The config and its one CI consumer have been mutually consistent this
   whole time; the drift is only visible against the real, current
   `pcb/temper.kicad_pcb`, which this test never touches.
2. **Even that test ran with zero PCL constraints active for ~3 days.** Per
   PR #1026: `_load_pcl_constraints`/`_load_zones` swallowed all load errors
   (`except Exception: return []`, added 2026-07-18) — harmless until
   2026-08-08's schema guard (`e557004d4`) started rejecting the config's own
   `version`/`metadata`/`netclasses` keys, at which point every run silently
   solved with **zero** constraints while the test's own comment claimed
   "solve placement with all constraints active." Fixed by #1026
   (2026-08-11), same day this task started.
3. **Even with the swallow fixed, `test_golden_board_drc_regression`
   downgrades unresolved refs to a `warn` policy** (`_downgrade_unresolved_ref_policy`,
   patching `_encoder_core._UNRESOLVED_REF_POLICY`) before running — meaning
   `J_AC_IN`/`J_COIL`/`J_DEBUG`/`Q1`/`Q2` are silently skipped, not enforced,
   even in the one path that runs this config with kicad-cli present.

### 1.5 The board's *actual* placement was never produced by this config at all

`pcb/temper.kicad_pcb`'s current placement comes from commit `68818da9`
(2026-07-27, "re-solve resynced temper board with domain-clearance
constraints") — an **auto-generated** set of 7,715 `SEPARATED` constraints
derived from domain/net-class classification, unrelated to
`temper_induction_cooker.yaml`'s hand-authored adjacency/zone intent
(commutation-loop minimization, shared-heatsink proximity, HV/MCU zone
containment). Separately, `placer/cp_sat/isolation_barrier.py` (671 lines,
fully tested, confirmed feasible at PD2/8.0mm per
`docs/plans/2026-08-11-002-feat-placer-wirelength-and-hv-separation-plan.md`)
implements barrier-respecting placement but is reachable only via an
`isolation_barrier=` kwarg **never passed by production**.

**This is the H2 half of the picture**: for the constraints whose engineering
rationale is still live (see table), the board is not "wrong" in the sense of
having drifted away from a placement that once satisfied the config — it
*never once* was placed under this config's intent, mechanically or via the
barrier-aware solver that could enforce the safety-relevant parts of it. The
config was never fully "in the loop," so "the board violates the config" and
"the config is aspirational and correct" look identical from inside this repo
until you check whether the placement pipeline that produced the board ever
consumed the config at all. It didn't.

---

## Part 2: per-constraint verdict (all 21)

Component identities and measured distances below are PR #1026's
independently-derived table (direct `pcb/temper.kicad_pcb` sheetpath reads,
cross-checked against `temper_constraints.references.yaml`), reused here
rather than re-measured, plus the H1/H2/H3 classification this task adds.
"Real ref" = the board component the alias manifest / PR #1026 both document
as the config's actual intent, where determinable.

| # | Constraint | Refs (named → real) | Requirement | Measured | Verdict | Evidence |
|---|---|---|---|---|---|---|
| 1 | `loop_area commutation_loop` | loop `commutation_loop` | ≤500mm² | n/a | **UNRESOLVABLE** | `auto_extract_loops()` finds no production loop for this netlist; `loop_aliases: {}`, `unresolved_loops` explicitly lists it. A data/tooling gap, not evidence the *limit* is stale — but nothing today can evaluate it either way. |
| 2 | `loop_area gate_drive_high` | loop `gate_drive_high` | ≤100mm² | n/a | **UNRESOLVABLE** | Same cause. Note: `references.yaml`'s `unresolved_loops` key is `high_side_gate_loop`, not `gate_drive_high` — the manifest's own loop-name reconciliation doesn't even line up with this config's names, a second-order sign the loop side of this config was never reconciled the way the component side was. |
| 3 | `loop_area gate_drive_low` | loop `gate_drive_low` | ≤100mm² | n/a | **UNRESOLVABLE** | Same cause (manifest key `low_side_gate_loop`, same name mismatch). |
| 4 | `adjacent Q1/Q2` (`adj_Q1_Q2`) | Q1→U5, Q2→U6 (IGBTs, `hb.power_loop.q_high`/`q_low`) | ≤10mm edge-to-edge | U5–U6 ≈91.5mm edge-to-edge (≈106mm center-center); not x-aligned (70.9mm apart) | **AMBIGUOUS — escalate** | Resolution is credible and twice-independently verified (references.yaml 2026-08-01 + PR #1026 2026-08-11, both reading board `sheetpath`). Gap is far too large for a stale-threshold reading. `elec/domain_manifest.yaml` keeps both IGBTs in the same `hb` half-bridge domain (no isolation split between them was added) — nothing found suggests the ≤10mm shared-heatsink rationale stopped applying. But per §1.5, the board's placement was never solved under this constraint at all. **Cannot distinguish "constraint is right and placement is simply wrong" from "the half-bridge's physical layout intentionally changed and the constraint is stale" without EE sign-off on current heatsink/thermal design** — see Open Questions. |
| 5 | `adjacent U_GATE/Q1` | U_GATE→U7, Q1→U5 | ≤15mm | U7–U5 ≈100.2mm | **STILL-VALID-INTENT, unsatisfied** | Alias resolves cleanly (`component_aliases`). Gate-driver-to-switch proximity is basic power electronics; no evidence the requirement itself changed. Same root cause as #4 — never placed under this config. |
| 6 | `adjacent C_BUS1/Q1` | C_BUS1→C2, Q1→U5 | ≤20mm | C2–U5 ≈169.5mm | **STILL-VALID-INTENT, unsatisfied** | Alias resolves cleanly. Same root cause as #4/#5. |
| 7 | `adjacent C_BUS2/Q2` | C_BUS2→C3, Q2→U6 | ≤20mm | C3–U6 ≈107.0mm | **STILL-VALID-INTENT, unsatisfied** | Same. |
| 8 | `separated HV_ZONE/MCU_ZONE` | zones only | ≥10mm | zone bounds are `[0,0,100,70]`/`[0,80,100,150]` — sized/positioned for the pre-2026-07-25 placeholder board | **STALE ZONE GEOMETRY — DO NOT EDIT, escalate** | §1.3 proves the bounds tracked a real board as of 2026-07-11 and never updated. Per task boundaries, this is the mains↔SELV isolation boundary on a live-mains board; a mechanical resize risks laundering a real safety defect (see #19) into a passing check. Owner has separately settled PD2/8.0mm creepage today and is adding the sealed compartment — this constraint's fate is tied to that work, not a placer-config edit. |
| 9 | `separated J_AC_IN/U_MCU` | J_AC_IN → **no board ref** | ≥15mm | n/a | **UNRESOLVABLE** | `unresolved_components`: "no source-backed connector instance." J_AC_IN was a real designator through 2026-07-11 (§1.3) but the 2026-07-15 real-netlist resync has no AC-input connector *of any name* in the current design (`elec/exports/temper.design-input.v1.json`'s only 3 dummy components are `Q1`/`Q2`/`U_MCU` — see note below on that file's own reliability). Whether AC power now enters via a non-header mechanism (screw terminal, direct wire, not yet modeled as a placeable component) or is a genuine missing part is a board-completeness call this task cannot make. |
| 10 | `separated U_MCU/Q1` | U_MCU→U27, Q1→U5 | ≥30mm | U27–U5 ≈174.2mm | **STILL-VALID-INTENT, satisfied** | Passes regardless of the Q1 ambiguity (any real IGBT candidate clears 30mm by a wide margin). Low priority. |
| 11 | `separated U_MCU/Q2` | U_MCU→U27, Q2→U6 | ≥30mm | U27–U6 ≈103.9mm | **STILL-VALID-INTENT, satisfied** | Same as #10. |
| 12 | `on_side Q1,Q2 top/flush` | Q1→U5, Q2→U6 | top edge, flush | U5 y≈218.7 (near top of 234mm board); U6 y≈139.3 (mid-board) | **AMBIGUOUS — escalate** | Same root identity question as #4. U5 roughly satisfies "top edge"; U6 clearly does not. Consistent with "never placed under this constraint," not with "constraint no longer applies" (both are still TO-247 parts needing edge/heatsink access per the board's own BOM). |
| 13 | `aligned Q1,Q2 horizontal` | Q1→U5, Q2→U6 | ±1mm | x: U5=3.7, U6=74.6 (70.9mm apart) | **AMBIGUOUS — escalate** | Same as #4/#12. |
| 14 | `separated Q1/MAX31865` | Q1→U5, MAX31865→U9 | ≥40mm | U5–U9 ≈60.1mm | **STILL-VALID-INTENT, satisfied** | Passes. Low priority. |
| 15 | `separated C_BUS1/Q1` (thermal) | C_BUS1→C2, Q1→U5 | ≥15mm | C2–U5 ≈169.5mm | **STILL-VALID-INTENT, satisfied — but see note** | Passes the *minimum*, but note this is the same C_BUS1/Q1 pair as #6, which wants them **within 20mm** for EMI. The current 169.5mm separation blows through the narrow 15–20mm feasible window on both constraints simultaneously in the "too far" direction — strong independent confirmation that this pair's placement was never tuned to *any* reading of this config, stale or otherwise. |
| 16 | `on_side J_AC_IN,J_COIL top/overhang` | both → **no board ref** | top edge, overhang | n/a | **UNRESOLVABLE** | Same connector-existence gap as #9/#17. |
| 17 | `separated J_AC_IN/J_COIL` | both → **no board ref** | ≥20mm | n/a | **UNRESOLVABLE** | Same. |
| 18 | `on_side J_DEBUG bottom/overhang` | J_DEBUG → **no board ref** | bottom edge, overhang | n/a | **UNRESOLVABLE** | The current board's only header-style connector, `J1`, is `thermal.j_fan` (confirmed: `grep '"Reference" "J' pcb/temper.kicad_pcb` returns only `J1`) — not a debug connector under any name. Debug access may now be test points/pogo pins not modeled as a discrete component, or may be a genuine gap; not determinable from this repo's artifacts. |
| 19 | `enclosing HV_ZONE` (inner: Q1,Q2,C_BUS1,C_BUS2,J_AC_IN,J_COIL,U_GATE,C_BOOT) | mixed (see above) | contained in HV_ZONE | **C_BUS1(C2)/C_BUS2(C3) sit inside the zone currently labelled `MCU_ZONE`**, not `HV_ZONE`, under current (stale) bounds; Q1/Q2/J_AC_IN/J_COIL unresolved | **SAFETY — DO NOT EDIT, escalate** | This is the constraint the task brief specifically flags: if the zone bounds are authoritative and the HV bus caps are genuinely inside `MCU_ZONE`, "fix the constraint to match the board" would launder a placement safety defect into a passing check. Reported, not touched. |
| 20 | `enclosing MCU_ZONE` (inner: U_MCU, MAX31865, J_DEBUG) | U_MCU→U27 (in), MAX31865→U9 (out), J_DEBUG unresolved | contained in MCU_ZONE | U27 is inside the declared `MCU_ZONE` bounds; **U9 (MAX31865) is outside both declared zones entirely**, near the board's far top edge (y≈229.9 of 234) | **SAFETY — DO NOT EDIT, escalate** | Same zone-geometry staleness as #8/#19/#21, plus an independent finding: MAX31865 sits outside *both* zones regardless of which bounds are used, which is not explained by the zone-resize question alone. |
| 21 | `keepout ISOLATION_BARRIER` | zone only | keepout, 10mm strip | zone is `100mm`-wide × `10mm` on a board that is actually `152mm` wide — doesn't span the board | **SAFETY — DO NOT EDIT, escalate** | Same stale-geometry proof as §1.3. Explicitly out of scope per task boundaries: owner has settled PD2/8.0mm creepage today, and a sibling agent is landing the sealed-compartment gate; this constraint's real fix is downstream of that work, not a placer-config edit. |

**Tally:** 3 UNRESOLVABLE (loop data gap) + 5 UNRESOLVABLE (connector doesn't
exist) + 3 AMBIGUOUS/escalate (Q1/Q2 identity+placement) + 4 SAFETY/escalate
(zone geometry, do not edit) + 6 STILL-VALID-INTENT already satisfied +
3 STILL-VALID-INTENT unsatisfied (real violations, not config defects) = 21.
No STALE-with-safe-fix items were found.

**What was landed in this PR: nothing in `temper_induction_cooker.yaml`.**
Every one of the 21 constraints is either a forbidden HV/zone touch, an
ambiguous identity question, or a board-completeness call outside this task's
authority. The task's own permission ("land constraints you can prove are
stale *and* whose fix is unambiguous") was checked against all 21 and found
to apply to none of them — the zone bounds are provably stale but their fix
is explicitly forbidden territory (safety), and the component-reference drift
that *is* unambiguous (the renamed parts) is already handled by
`temper_constraints.references.yaml`'s `component_aliases`, not by editing
this file.

---

## Open questions for the owner

1. **`adj_Q1_Q2` (and its two siblings #12/#13, plus #4-adjacent #5/#6/#7):
   is the ≤10mm/±1mm/top-edge intent for the IGBT pair still correct, or did
   the half-bridge's physical/thermal layout change since Dec 2025?**
   `elec/domain_manifest.yaml` keeps both IGBTs in the same `hb` domain (no
   isolation split added between them), which argues the constraint is still
   correct and the board's placement simply never tried to satisfy it — but
   only a human with the current thermal/heatsink design can confirm that.
   **What would settle it:** a heatsink/enclosure drawing or thermal design
   note stating whether U5/U6 are still meant to share one heatsink zone. If
   yes, this is a genuine placement defect the CP-SAT placer should be asked
   to fix (ideally via a run that actually consumes this PCL config, not the
   domain-clearance auto-generated set that currently drives placement). If
   no, the constraint itself needs rewriting with EE input — not something
   this task can determine unilaterally.
2. **`enc_HV_ZONE` / HV bus caps in `MCU_ZONE`-labelled geometry (#19), plus
   MAX31865 outside both zones (#20): is this a live safety defect on the
   real board, or an artifact of the zone bounds being stale?** Both are true
   simultaneously — the zone bounds are provably stale (§1.3), *and* nothing
   found in this repo shows the bus capacitors were ever deliberately placed
   relative to any HV/SELV boundary (§1.5: the board's placement never ran
   under barrier-aware constraints at all). Resizing the zones to the real
   152×234mm board would make this check pass without knowing whether the
   caps are actually creepage-safe from the SELV side under PD2/8.0mm. **This
   needs the sealed-compartment/PD2 work (in flight on a sibling branch) to
   land first**, so the zone's real position can be derived from the
   enclosure geometry rather than guessed.
3. **`J_AC_IN`/`J_COIL`/`J_NTC`/`J_USB`/`J_DEBUG` (#9, #16, #17, #18): were
   these connectors dropped by design (e.g. screw terminals not yet modeled
   as placer components) or are they missing parts?** The current board has
   exactly one connector, `J1` (a fan connector). `elec/exports/temper.design-input.v1.json`
   — the file `temper_constraints.references.yaml`'s `authority.source_export`
   names as ground truth — is itself a 3-component stub (`Q1`, `Q2`,
   `U_MCU` only, board `100×150mm`) dated 2026-07-11, not a real export of the
   current 169-component design; it cannot answer this question either. This
   is a connector-BOM ownership call, same conclusion PR #1026 reached.

## Secondary finding (not acted on, out of the 21-constraint scope)

The file's own already-**disabled** `D_BOOT`/`C_BOOT` comment (line ~130)
claims `D_BOOT` is "absent from the current netlist." Per
`temper_constraints.references.yaml` and confirmed via the board's own
`sheetpath`, `D_BOOT` **does** exist, as `U8` (`hb.gate_hs.boot_diode`) — the
comment itself is stale. This constraint is not active (already `#`-commented
out), so it's outside this task's per-constraint scope, and PR #1026 flagged
the same thing without acting on it. Worth a human pass over the
already-disabled constraints as a separate follow-up.
