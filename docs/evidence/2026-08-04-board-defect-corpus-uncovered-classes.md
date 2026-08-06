# Provenance: measured against origin/main at the commit below; the tracked
# tree carried this investigation's own edits at measurement time.
provenance: commit=838096820b30ca3999aaa76fffa9ea736c6c89a0 dirty=true

# Board-defect corpus: two uncovered classes diagnosed and closed (R38 / R9 / R26)

<!-- provenance: commit=838096820b30ca3999aaa76fffa9ea736c6c89a0 dirty=true -->

**Date:** 2026-08-04
**Scope:** `pcb/temper.kicad_pcb` read-only throughout -- every measurement below is taken on a
run-time *copy*. `power_pcb_dataset/drc_ceiling.json` read-only and unchanged; no
`Ceiling-Approval:` trailer is authored by this work.

## 0. The reported failure

```
[FAIL] off-board: off-board: uncovered class -- no owning gate fired: courtyard...
[FAIL] pad-short: pad-short: uncovered class -- shorting_items did not rise
[PASS] creepage: creepage: owning gate req-safe-01-creepage-dc-lv fired: DC...
Board-defect corpus: FAIL -- 1/3 classes covered
```

Three hypotheses were considered per class: (1) the gate exists but the corpus does not run it or
reads the wrong field; (2) the gate does not exist; (3) the mutation does not produce the defect it
claims, so "no gate fired" is correct behaviour and the corpus is what is broken.

**Verdict: `off-board` is (2). `pad-short` is (1). Hypothesis (3) is ruled out for both** -- both
mutations were confirmed to produce a genuinely defective board, by reading the mutated files
directly (Sec. 2). The seed-hash staleness is real and is what *unmasked* the `off-board` hole, but
it is not the cause of either failure, and re-seeding alone fixes neither.

## 1. Measurement environment

| | |
|---|---|
| kicad-cli | **10.0.4** (local). CI runs 10.0.5; geometric DRC counts differ between them, so no count below may be compared against a CI-recorded number. |
| DRC invocation | `kicad-cli pcb drc --all-track-errors --format json`, the canonical `run_drc` path, with the SSOT-regenerated `temper.kicad_dru` placed beside each board copy. |
| Board under test | `pcb/temper.kicad_pcb` @ `origin/main` `8380968`, sha256 `51e39844…`. |
| Repetitions | N=11 for every count-based claim (Sec. 4). |

All clean-vs-mutated comparisons are made **within one environment**, which is exactly the
comparison the corpus itself makes.

## 2. Hypothesis (3) ruled out first: the mutations do produce their defects

The seed manifest recorded `board_sha256: e2fb9237…` (commit `54372bbf`, 2026-07-29). The committed
board is `51e39844…`. The mismatch is real and had also broken
`test_manifest_board_hash_matches_committed_board`.

The staleness is worse than a single relay swap. Comparing the seed-era board against today's:

| | seed board `54372bbf` | today `de59c0458` |
|---|---|---|
| footprints | 169 | 169 |
| **footprints whose position changed** | — | **all 169** |
| C26 (`tank.c_tank2`) | (59.38, 28.75) rot 0 | (65.92, 72.32) rot **270** |
| C28 (`ct_sense`, 0603) | (21.98, 140.07) rot 0 | (41.69, 21.98) rot 90 |

The corpus was *authored* on 2026-08-02 against a 2026-07-29 board that `main` had already moved
past: `55226f8ad` (#517, 2026-07-31) re-solved the whole placement, and `829af5c59`/`27ea686c5`,
`a2fdfd1bb` (#568) and `de59c0458` (#602) each changed it again. The corpus has therefore never
been green against the board it is committed alongside.

Both mutations were then inspected on the *mutated files themselves*, not inferred from counts:

* **off-board** — C26 is written at `(59.38, 256.0)`. The Edge.Cuts outline is unchanged at
  `(20,20)-(172,254)`. Pad 1 lands at `(59.38, 256.0)` and pad 2 at `(59.38, 296.0)`; both are
  **fully outside** the outline, 0.162 mm and 40.162 mm clear of it. The defect is present.
* **pad-short** — C28 pad 2 is written at pad 1's exact local position `(-0.775, 0)`, both pads
  `roundrect 0.9 x 0.95` on `F.Cu`, nets left distinct (`I_SENSE` / `gnd`). The defect is present,
  and KiCad agrees: it reports `Clearance violation (rule 'Fine pitch IC pads' clearance 0.1000 mm;
  **actual 0.0000 mm**)` between the two pads.

So the boards are defective, and re-seeding does not change either verdict.

## 3. `off-board`: hypothesis (2) — the gate does not exist

The manifest named `courtyards_overlap` and `copper_edge_clearance` as the class's owning gates,
describing them as "the standing proxy for the R26 containment invariant until R26 lands". Neither
checks containment, and measured on both boards neither is a proxy for it:

| owning gate | seed board clean → mutated | today clean → mutated |
|---|---|---|
| `copper_edge_clearance` | 15 → 15 (**never fired, ever**) | 12 → 12 |
| `courtyards_overlap` | 14 → **29** | 11 → 11 |

`copper_edge_clearance` measures copper too *close* to the edge; copper that has left the board is
simply far from it, so the rule has nothing to say. `courtyards_overlap` fired on the seed-era board
by pure coincidence of geometry: C26 was at rot 0 there, so the move laid its 40 mm-pitch axial body
flat across a populated region and collided with 15 courtyards. At rot 270 the same move drops it
into empty space and the count does not change.

**The perverse result.** Full category delta on today's board, clean → off-board mutated:

```
hole_clearance      105 -> 102
shorting_items      200 -> 197
solder_mask_bridge  154 -> 151
```

Throwing a component off the edge of the board **improves DRC by 9 errors**, because its copper
stops colliding with the rest of the layout. No count-delta assertion can ever detect this class,
and under a purely count-based ratchet, deleting a component is *rewarded*.

A repo-wide search confirms no containment gate existed: `zone_containment.rs` is about copper
zones, not the outline, and `validation/netlist_reconciliation.py` explicitly defers the class —
"the off-board staging is a containment defect owned by the R26 plan, not this reconciliation".
R26 (`docs/plans/2026-08-02-001`) is "every component inside the outline", still unlanded.

**Fix: `scripts/check_board_containment.py`**, a real gate. Every pad's copper polygon — rotated by
the sanctioned KiCad convention (`temper_placer.geometry.kicad_transform`, R(-theta); the formula is
never retyped locally, per `check_no_raw_rotation_trig.py`) — must be covered by the Edge.Cuts
polygon. Pad copper is the checked surface rather than courtyard, because courtyards legitimately
overhang the outline on edge-mounted parts while copper outside the outline is not manufacturable at
all. Pad-less footprints are not skipped; their origin is checked instead.

**Independent validation of the geometry.** Run against the seed-era board, the gate reports C27's
two pads outside the outline at `(20.0, 272.75)` and `(60.0, 272.75)` — rediscovering, from
geometry alone, the "tank cap staged off-outline at `(at 20.0 272.75)`" that
`board_defect_corpus.yaml` and `netlist_reconciliation.py` both independently document as a real
known defect of that board.

## 4. `pad-short`: hypothesis (1) — the gate fires, the corpus read the wrong field

The seeded short *is* detected by DRC. The corpus did not see it, for three independent reasons —
each sufficient on its own.

**(a) The comparison was mathematically unsatisfiable.** `_baseline` required
`mutated > max(clean, recorded_ceiling)`. The `shorting_items` ceiling history:

| ceiling commit | date | `shorting_items` ceiling |
|---|---|---|
| `df84a9d04` | 2026-07-29 | **118** ← corpus authored against this |
| `68edddbcf` … `de59c0458` | 2026-07-31 → 08-03 | 202 → **201** |

When the corpus was written, clean measured 118 and the ceiling *was* 118, so a +1 delta cleared it.
After the re-solve the ceiling rose to 201 while clean measured 200 — so the mutation had to produce
**202** to be counted. A one-pad short cannot. The class was unsatisfiable from the moment the
ceiling moved, independent of any board defect.

**(b) The signal was inside the measurement's own noise floor.** N=11, kicad-cli 10.0.4:

| series | median | min | max | values |
|---|---|---|---|---|
| clean `shorting_items` | 199 | 199 | 200 | `199,199,199,199,200,199,200,199,199,199,199` |
| mutated `shorting_items` | 199 | 199 | 200 | `199,199,200,199,199,199,199,199,199,199,199` |
| **delta (mutated − clean)** | **0** | **−1** | **+1** | `0,0,1,0,-1,0,-1,0,0,0,0` |

The old assertion's entire signal is `+1`. The measurement's own run-to-run range on a
*byte-identical* board is `±1`. Even with a correct baseline, this assertion was coin-flipping.

**(c) The category is not stable for this defect.** The identical mutation is classified differently
depending on board state:

| board | how KiCad reports the C28 pad1↔pad2 overlap |
|---|---|
| seed-era `54372bbf` | `shorting_items` — "Items shorting two nets (nets I_SENSE and gnd)" |
| today `de59c0458` | `clearance` — "rule 'Fine pitch IC pads' clearance 0.1000 mm; **actual 0.0000 mm**" **+** `solder_mask_bridge` |

A single hard-coded category name cannot see a defect KiCad renames. On today's board there are
**zero** `shorting_items` naming C28 at all, mutated or clean.

**Fix: assert on identity, not on counts.** The class now requires that *some* DRC error names
**both** mutated pads on the mutated board, and that **none** does on the clean board. Measured N=11:

| series | median | min | max |
|---|---|---|---|
| clean: errors naming both C28 pad 1 and pad 2 | **0** | 0 | 0 |
| mutated: errors naming both C28 pad 1 and pad 2 | **2** | 2 | 2 |

Perfect separation, zero variance, category-independent. This is **stronger** than the count-delta
it replaces, not weaker: a count can rise for an unrelated reason anywhere on the board, but an
error naming the exact two pads the mutator moved cannot.

## 5. Result

Both classes now satisfy both halves of R9 — the gate fires on the seeded defect *and* is silent on
the clean board — verified through the corpus's own decision functions against real DRC output:

```
clean board: 842 DRC errors, containment refs outside: none

[off-board] ok=True
   owning gate board_containment fired: C26 has copper outside the Edge.Cuts
   outline on the mutated board and none on the clean board

[pad-short] ok=True
   owning gate kicad-drc fired: 2 DRC error(s) name both C28 pad 1 and pad 2 on
   the mutated board and none on the clean board [clearance: ... actual 0.0000 mm;
   solder_mask_bridge: ...]

anti-vacuity violations: none
clean DRC (corpus categories): {"courtyards_overlap": 11, "copper_edge_clearance": 12,
                                "shorting_items": 199}
```

`board_containment` on the clean board is `{}` and on the off-board mutant is `{C26}` in all 11
runs (it is pure geometry, so it is deterministic by construction).

### Counts that changed, and why that is the instrument improving

No DRC count on the committed board changed — `pcb/temper.kicad_pcb` is untouched and
`drc_ceiling.json` is unmodified. What changed is that **one new gate now reports on the board**
(`check_board_containment.py`), and it reports **zero violations** on the committed board today.
Per goal-set AE4, a future rise from this instrument is attributable to the instrument, not to a
regression — but there is no rise to attribute yet.

The corpus's own verdict moves from `FAIL -- 1/3 classes covered` to `3/3`, and the seed manifest is
re-stamped from `e2fb9237` to `51e39844` with the board change attributed in
`_meta.reseed_note`.

## 6. Not fixed here, deliberately

* The `creepage` class is unchanged. It was already passing and keeps its per-class count-delta
  against its documented known-finding baseline (the REQ-SAFE-01 gate is red on main).
* `power_pcb_dataset/drc_ceiling.json` is untouched, and no `Ceiling-Approval:` trailer is authored.
  The `shorting_items` ceiling of 201 sitting above the clean measurement of ~199-200 is real slack
  that a regression could hide in, but ratcheting it is R27's job and requires a measured sample and
  an attributed cause, not a drive-by edit from this investigation.
