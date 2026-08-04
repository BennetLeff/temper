<!-- provenance: commit=d3e99b153baff07f1a162856cd20ba0ac27be750 dirty=true (measured in the p1/board-defect-corpus worktree at the validation/p1-execution base commit; the committed board pcb/temper.kicad_pcb was byte-identical to HEAD throughout -- board sha256 e2fb92370da13554710e00857ad03a460340a2ee4f1782220f02c8c552c80277 -- only the corpus branch's own new files were uncommitted, none of them touching the board.) -->

# Board-Defect Mutation Corpus — first reproduction (R38)

Branch `p1/board-defect-corpus`, from `validation/p1-execution` at
`d3e99b153` (the commit whose board and ceiling state everything below was
measured against). Plan: `docs/plans/2026-08-02-024-feat-board-defect-mutation-corpus-plan.md`.

This document records the corpus's first live reproduction of all three
defect classes, the numbers behind each seed, and the review-fix decisions
that shaped the seeds.

---

## What the corpus proves, and how

The corpus takes the **committed** board (`pcb/temper.kicad_pcb`), applies
one deterministic defect mutation per class to a **run-time copy**, and
asserts each mutated copy fails its owning gate while the unmutated board
passes the corpus's clean-board control. The committed board is never
modified, so the DRC-ceiling re-measurement convention stays inert.

The three real defect instances are **already present** on the committed
board:

| Real defect | On the committed board |
|---|---|
| Tank cap staged off-outline | `C27` (`tank.c_tank3`) at `(at 20.0 272.75)`, y > 254 |
| Pad short | `C1 pad2 (ac_n) ↔ R7 pad2 (zcd)`, 120/120 DRC runs |
| Creepage crossing | DC_BUS↔LV_CONTROL, 99 violations via REQ-SAFE-01 (measured 2026-08-02) |

"Re-creating" these would be a no-op (the gate already fails for them), so
each seed starts from a **defect-free point** and is asserted with a
**count-delta**: mutated count > clean count (and, for DRC categories, >
the recorded `drc_ceiling.json` ceiling):

| Class (seed) | Mutation | Clean → Mutated | Owning gate |
|---|---|---|---|
| off-board (1) | `C26` (in-board tank cap) → `(59.38, 256.0)`, straddling the y=254 edge | `courtyards_overlap` 14 → **29** | `courtyards_overlap` / `copper_edge_clearance` DRC categories |
| pad-short (2) | `C28` pad 2 copper → pad 1 position (nets `I_SENSE` vs `gnd` stay distinct) | `shorting_items` 118 → **119** | `shorting_items` DRC category (`run_drc`, `--all-track-errors`) |
| creepage (3) | `C8` (DC_BUS_RTN 0603) → `(116.26, 138.72)`, ~2 mm from `C11` (LV_CONTROL) | DC_BUS↔LV_CONTROL creepage 99 → **102** | REQ-SAFE-01 creepage (per-class delta) |

The full run's output:

```
board sha256: e2fb92370da13554...
  matches manifest seed hash (corpus validated against this board)
clean-board DRC: {"clearance": 499, "shorting_items": 118, ...,
  "courtyards_overlap": 14, "copper_edge_clearance": 15, ...}
clean-board DC_BUS<->LV_CONTROL creepage: 99

anti-vacuity control (clean board at/below recorded ceilings):
  PASS

defect classes:
  [PASS] off-board: owning gate courtyards_overlap fired: 29 > baseline 14 (clean 14, ceiling 14)
  [PASS] pad-short: owning gate shorting_items fired: 119 > baseline 118 (clean 118, ceiling 118)
  [PASS] creepage: owning gate req-safe-01-creepage-dc-lv fired:
    DC_BUS<->LV_CONTROL creepage 99 -> 102 ...

Board-defect corpus: PASS -- 3/3 classes covered, clean board green
```

Measurement environment: `kicad-cli 10.0.4` (the DRC ceiling's own
recorded tool version), `temper_placer.validation._drc_api.run_drc`
(which bakes in `--all-track-errors`), `elec/build/default.net` compiled
from `elec/src/*.ato` via `make netlist` at `d3e99b153`.

---

## Review fixes folded in (differences from the plan's literal text)

1. **Seeds start from defect-free points, not the real instances.** The
   plan's U3 said "encode each real defect ... referencing the real
   components (tank.c_tank3 / board C27, C1 pad2 / R7 pad2, ...)". All
   three real instances are already on the committed board, so reproducing
   them changes nothing. Each seed instead moves an in-board footprint
   off-board (`C26`), shorts a not-yet-shorted pad pair (`C28` pad 1/2),
   and compresses a currently-compliant creepage pair (`C8`→`C11`), with
   count-delta assertions.

2. **A net-join cannot create a short.** The plan's U1 approach said
   "rewrite a pad's net ordinal to join another pad's net (pad short)".
   On a static board a `shorting_items` violation requires physically
   overlapping copper on *different* nets; rewriting one pad's net to
   another's only *removes* shorts. The pad-short mutation therefore moves
   `C28` pad 2's copper onto pad 1's position while keeping the two nets
   distinct — one new, deterministic shorting item, no net rewritten
   (verified: `mutated.nets_changed == 0`).

3. **The anti-vacuity control excludes the creepage gate.** The plan's U2
   said "the clean board must pass all gates". The REQ-SAFE-01 creepage
   gate is red on main today (99 DC_BUS↔LV_CONTROL violations), so the
   clean-board control is scoped to the corpus's DRC gate categories that
   ARE green (`courtyards_overlap` 14 ≤ 14, `copper_edge_clearance` 15 ≤
   15, `shorting_items` 118 ≤ 118) and the creepage class is asserted via
   per-class delta against its documented known-finding baseline. This is
   recorded in `scripts/board_defect_corpus.yaml`
   `classes.creepage.baseline_note`.

4. **Threshold note.** The plan quoted the handoff's "enforced at
   `design_value_mm` 10.0". The matrix the gate actually enforces
   (`IEC60335_REQUIREMENTS` in
   `temper_placer/requirements/validators/clearance.py`) gates on
   `min_creepage_mm` — 12.6 mm reinforced / 6.3 mm basic for
   DC_BUS↔LV_CONTROL after the PD3 correction — and `design_value_mm` is
   documentary only. The corpus measures through
   `verify_iec60335_compliance` (the REQ-SAFE-01 gate's own code path), so
   it tracks whatever threshold the gate actually enforces.

---

## Anti-vacuity scoping (why the creepage gate is excluded)

The clean-board control must only hold gates that are green on the clean
board. Asserting the creepage gate at zero would fail the corpus on a board
whose creepage state is a known, tracked finding — the exact "assert
something that cannot pass" failure this repo's gates exist to avoid. The
creepage class's bite is proven by the delta instead: the mutated board
must measurably worsen the already-known DC_BUS↔LV_CONTROL finding. If a
future placement re-solve makes the creepage gate green, the class can be
re-scoped to the strict gate (and the anti-vacuity control widened).

## Content-hash drift semantics

The seed manifest records `board_sha256 = e2fb92370da13554710e00857ad03a460340a2ee4f1782220f02c8c552c80277`
(the committed board, matching `drc_ceiling.json`'s own recorded input
hash). A board change makes the runner's hash mismatch the manifest's; the
runner warns, re-derives every mutated board from the new content, and
re-validates every seed in the same run — a seed that stops reproducing its
class fails the corpus. After a green run on changed board content, the new
hash is stamped with `--update-manifest`.
