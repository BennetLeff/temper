# Provenance: measured against the commit below; the tracked tree carried
# this investigation's own edits (this document's own change set) at
# measurement time.
provenance: commit=90d5fd983f825d1895f416b8535dee6a169b8979 dirty=true

<!-- provenance: commit=90d5fd983f825d1895f416b8535dee6a169b8979 dirty=true -->

# Board-defect corpus: clearance and courtyard classes closed (R38 / R9 / R10)

**Date:** 2026-08-07
**Scope:** `pcb/temper.kicad_pcb` read-only throughout -- every measurement below is taken on a
run-time *copy*, exactly as the existing `off-board`/`pad-short`/`creepage` classes do.
`power_pcb_dataset/drc_ceiling.json` read-only and unchanged; no `Ceiling-Approval:` trailer is
authored by this work.

## 0. The gap this closes

A goal-set audit (docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md, R9/R10) found the
board-defect mutation corpus (`scripts/board_defect_corpus.yaml` /
`scripts/check_board_defect_corpus.py`) VACUOUS for two of the five safety-critical constraint
families:

* **Clearance** -- `packages/temper-drc-rs/src/rules/drc/clearance.rs`'s `ClearanceCheck` and
  `router_clearance.rs` exist and have unit tests, but the corpus had NO clearance mutation class.
  Clearance appeared only incidentally in the `pad-short` mutation's kicad-cli output (a same-
  footprint "Fine pitch IC pads" 0.1mm rule -- RULE 1 in `generate_kicad_dru.py` -- not an ordinary
  inter-component clearance defect). Only synthetic unit fixtures existed
  (`packages/temper-placer/tests/requirements/safety/test_clearance.py`).

* **Courtyard** -- worse, and self-documented:
  `docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md` recorded that
  `courtyards_overlap` was MEASURED not to discriminate the seeded `off-board` defect (11 -> 11,
  unchanged) and was explicitly DROPPED as an owning gate that date. No replacement gate was ever
  assigned. Referenced from `scripts/check_board_defect_corpus.py:20-35` (pre-2026-08-07 line
  numbers) as an open item.

This document adds a real, deterministic mutation class for each, demonstrates a genuine
before/after separation through the corpus's own decision functions (not a hand-run subset), and
records why each is now SOUND rather than VACUOUS.

## 1. Measurement environment

| | |
|---|---|
| kicad-cli | **10.0.5** (locally extracted from the `ppa:kicad/kicad-10.0-releases` `.deb` plus its non-preinstalled runtime deps -- `libgit2-1.7`, `libnng1`, and the `libocct-*` OpenCASCADE set -- from the Ubuntu archive; no root available in this sandboxed environment, so nothing was installed system-wide). This matches CI's pinned version (`.github/docker/ci.Dockerfile`, `KICAD_VERSION=10.0.5~ubuntu24.04.1`), NOT the `10.0.4` the 2026-08-04 doc and several `_march` entries were measured against -- per that doc's own environment note and `AGENTS.md`, geometric DRC counts are not comparable across kicad-cli versions, so every count below is a same-environment clean-vs-mutated comparison, never a cross-version one. |
| DRC invocation | `temper_placer.validation._drc_api.run_drc` -- the canonical path (`kicad-cli pcb drc --all-track-errors --format json`, thread-pinned to `MaximumThreads=1` via a throwaway `KICAD_CONFIG_HOME`), identical to what `scripts/check_board_defect_corpus.py` and the DRC ratchet use. |
| Board under test | `pcb/temper.kicad_pcb` @ this document's provenance commit, sha256 `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6` (the manifest's `board_sha256` was stale at `51e39844...`, commit `de59c0458`; re-stamped by this change via `--update-manifest` after a green run, per the manifest's own documented convention -- the board itself is untouched, only its recorded hash in the seed manifest). |
| Repetitions | N=120 for both new classes' identity signal AND the raw DRC category totals they sit inside (`clearance`, `courtyards_overlap`) -- see Sec. 4. |

## 2. Design constraint: do not repeat either prior failure mode

Two independent traps are documented for this corpus and both had to be avoided:

1. **The courtyard trap (2026-08-04, off-board class):** a mutation whose courtyard collision is an
   *accident* of unrelated placement geometry stops working the moment the board is re-solved.
   `courtyards_overlap` itself is not the problem -- the `off-board` mutation was never designed to
   produce a courtyard collision in the first place.
2. **The noise-floor trap (2026-08-04, pad-short class):** a signal smaller than a DRC category's
   own run-to-run variance is worthless, and `clearance` is this repo's OWN documented
   nondeterministic category (`AGENTS.md`'s DRC-ceiling section: "observed max + 1 headroom",
   >=120 samples required precisely because it moves on a byte-identical board).

Both new classes are therefore designed the same way, addressing both traps at once:

* **Deterministic-by-construction geometry.** Each mutation computes its target position FROM the
  real board's own footprint/pad/courtyard geometry (read via `kiutils`, the same
  `kicad_transform` rotation convention used everywhere else in this codebase), not from a
  coincidence of an unrelated defect's placement. See Sec. 3 for the exact numbers.
* **Identity, not count-delta, from the start.** Following the `pad-short` fix's own conclusion
  ("strictly stronger than a count-delta: a count can rise for an unrelated reason, but a finding
  naming the exact ref/pads the mutator touched cannot"), both classes assert that a DRC error
  names the exact seeded ref/pad pair -- immune to whatever the surrounding category count does.
  `errors_naming_two_pads` generalizes the existing `errors_naming_pad_pair` (same-footprint,
  pad-short) to two DIFFERENT footprints (clearance); `errors_naming_both_refs` checks the already-
  deduped `error.components` list, because courtyard violations are footprint-level ("Footprint
  R48"), not pad-level.

## 3. The two new mutations

### 3.1 `clearance`

**Owning gate:** `kicad-drc` (the ordinary, per-net-class `clearance` DRC category -- distinct from
both `pad-short`'s same-footprint "Fine pitch IC pads" 0.1mm exception and `creepage`'s HV<->SELV
custom DRU rule).

R67 (0603, pad 1 net `+3V3` / netclass `FinePitch` 0.1mm, pad 2 net
`safety.coil_thermal.comp-inp`; originally at `(101.37, 144.9)` rot 180, 36.1mm from the anchor) is
moved to `(134.66, 140.1)`, rotation unchanged. This places R67 pad 1 exactly 0.05mm from the FIXED
R64 (0603, pad 1 net `safety.thermal.comp-inp` / netclass `Default` 0.2mm, pad 2 net
`safety.thermal-line`; NOT moved, at `(137.16, 140.1)` rot 0) pad 1 -- below the applicable
requirement (KiCad enforces the MAX of the two nets' netclass clearances: `max(0.1, 0.2) = 0.2mm`
here) but strictly positive, so no copper overlap (unlike `pad-short`, which drives the gap to
exactly 0.0mm). Both R64 and R67 sit >=4.9mm from every other footprint at the mutated position, so
this is the only pair affected.

Measured kicad-cli output on the mutated board, verbatim:

```
clearance :: Clearance violation (netclass 'Default' clearance 0.2000 mm; actual 0.0500 mm)
    Pad 1 [safety.thermal.comp-inp] of R64 on F.Cu
    Pad 1 [+3V3] of R67 on F.Cu
```

No error names both R64 pad 1 and R67 pad 1 on the clean board (checked directly, not inferred).

### 3.2 `courtyard`

**Owning gate:** `kicad-drc` (`courtyards_overlap`) -- the SAME DRC category the 2026-08-04 doc
dropped, now correctly owning a mutation designed for it.

C38 (0603, originally at `(21.24, 203.44)` rot 90, far from the anchor) is moved to
`(41.54, 189.55)`, rotation unchanged. Its `F.CrtYd` courtyard rectangle (an `FpRect`, local
`[-1.48, 1.48] x [-0.73, 0.73]`mm, rotated the same `kicad_transform` way as every pad in this
module) then overlaps the FIXED R48 (0603 at `(41.54, 187.57)` rot 180; NOT moved) courtyard
rectangle by ~0.23mm in Y, while every pad pair between the two stays >=0.28mm apart -- above every
applicable net-class clearance (`Default` 0.2mm, `FinePitch` 0.1mm) -- so `courtyards_overlap` is
the ONLY violation this mutation produces between C38 and R48; no confounding clearance/short from
the same pair.

Measured kicad-cli output on the mutated board, verbatim:

```
courtyards_overlap :: Courtyards overlap
    Footprint R48
    Footprint C38
```

No error names both R48 and C38 on the clean board.

This directly addresses the 2026-08-04 finding rather than repeating it: that finding was that
`off-board`'s courtyard collision was an ACCIDENT of the pre-#517 board's geometry (C26 at rot 0
happened to lay its 40mm-pitch body across a populated region) and stopped working the moment the
board was re-solved (rot 270, empty space, 11 -> 11). This mutation instead computes its target
FROM the two footprints' own courtyard geometry, so the collision is a property of the seed, not an
accident of unrelated placement.

## 4. Stability: N=120 samples, both new classes, both the identity signal AND the raw category

Per the noise-floor trap above, the identity signal is the class's actual assertion and the raw
category totals below are supplementary context, not something either class relies on. Measured via
the SAME `run_drc()` path the corpus itself calls, 120 independent invocations per board (three
boards: clean, `clearance`-mutated, `courtyard`-mutated):

| board | errors naming BOTH R64 pad 1 and R67 pad 1 | errors naming BOTH R48 and C38 | `clearance` total | `courtyards_overlap` total |
|---|---|---|---|---|
| clean | **0** (120/120 runs) | **0** (120/120 runs) | 339 (120/120 runs) | 11 (120/120 runs) |
| `clearance`-mutated | **2** (120/120 runs) | 0 (120/120 runs) | 340 (120/120 runs) | 12 (120/120 runs) |
| `courtyard`-mutated | 0 (120/120 runs) | **1** (120/120 runs) | 341 (120/120 runs) | 12 (120/120 runs) |

Every column has **zero observed variance** across all 120 runs of every board -- both the identity
signal each class actually asserts, and (in this sample) even the raw category totals that
`AGENTS.md` documents as historically noisy elsewhere on this board. This is consistent with the
2026-08-04 thread-pinning fix in `_drc_api.py` (`_single_threaded_kicad_env`, `MaximumThreads=1`)
having closed most of the run-to-run scheduling-order variance that produced the old +/-1 range; a
residual pointer-address-keyed dedup source is still documented as theoretically possible
(`_drc_api.py`'s own comment, KiCad issue #20048), which is exactly why the design does not lean on
the raw counts at all -- the identity signal is immune to it either way.

`clearance`-mutated also shows the pad-short precedent's own caution is worth restating: the
category *did* rise here (339 -> 340), so in isolation this class *could* have used a count-delta
and it would have worked in this one sample. It is asserted by identity anyway, on principle -- the
same category is also the one `AGENTS.md` calls out as nondeterministic, and a class that only
passes because today's particular sample happened to be clean is exactly the kind of near-miss this
whole investigation exists to eliminate.

## 5. Full corpus run (5/5 classes, real run, not a hand-picked subset)

```
board sha256: 1cce4a0872051675...
  matches manifest seed hash (corpus validated against this board)
clean-board DRC: {"solder_mask_bridge": 154, "via_diameter": 4, "drill_out_of_range": 4,
                  "copper_edge_clearance": 10, "courtyards_overlap": 11,
                  "pth_inside_courtyard": 1, "clearance": 339, "shorting_items": 199,
                  "hole_clearance": 105, "tracks_crossing": 1}
clean-board DC_BUS<->LV_CONTROL creepage: 0
clean-board containment (refs with copper outside the outline): none

anti-vacuity control (clean board at/below recorded ceilings):
  PASS

defect classes:
  [PASS] off-board: owning gate board_containment fired: C26 has copper outside the Edge.Cuts
         outline on the mutated board and none on the clean board
  [PASS] pad-short: owning gate kicad-drc fired: 2 DRC error(s) name both C28 pad 1 and pad 2
         on the mutated board and none on the clean board
  [PASS] creepage: owning gate req-safe-01-creepage-dc-lv fired: DC_BUS<->LV_CONTROL creepage
         0 -> 6 (documented known-finding baseline: gate red on main; class asserted via
         per-class delta)
  [PASS] clearance: owning gate kicad-drc fired: 1 DRC error(s) name both R67 pad 1 and R64
         pad 1 on the mutated board and none on the clean board [clearance: Clearance
         violation (netclass 'Default' clearance 0.2000 mm; actual 0.0500 mm)]
  [PASS] courtyard: owning gate kicad-drc (courtyards_overlap) fired: 1 DRC error(s) name both
         C38 and R48 on the mutated board and none on the clean board [courtyards_overlap:
         Courtyards overlap]

Board-defect corpus: PASS -- 5/5 classes covered, clean board green
```

`DC_BUS<->LV_CONTROL creepage` measures 0 on the clean board today (not the 99 the 2026-08-02
`creepage` class baseline_note documents) -- the REQ-SAFE-01 gate has since gone green on `main`
(see `packages/temper-placer/tests/requirements/safety/test_clearance.py`'s 2026-08-02b docstring
update); the `creepage` class still fires correctly (0 -> 6) and is unaffected by this change,
consistent with task instructions not to touch that class.

## 6. Verdicts

| class | owning gate | clean | mutated | N | observed range | verdict |
|---|---|---|---|---|---|---|
| clearance | kicad-drc (`clearance` category, identity: R64 pad 1 + R67 pad 1) | 0/120 name the pair | 2/120 name the pair, every run | 120 | zero variance both boards | **SOUND** |
| courtyard | kicad-drc (`courtyards_overlap`, identity: R48 + C38) | 0/120 name the pair | 1/120 name the pair, every run | 120 | zero variance both boards | **SOUND** |

Both classes satisfy both halves of R9 (the gate fires on the seeded defect and is silent on the
clean board) with a demonstrated failing case, verified through the corpus's own decision functions
against real DRC output, not a synthetic fixture -- closing the R10 vacuity finding for both
families.

## 7. Not fixed here, deliberately

* `pcb/temper.kicad_pcb` is untouched; every mutation in this document runs against a run-time copy,
  exactly as `off-board`/`pad-short`/`creepage` already do.
* `power_pcb_dataset/drc_ceiling.json` is untouched, and no `Ceiling-Approval:` trailer is authored.
  The corpus's clean-board anti-vacuity control (`courtyards_overlap`/`copper_edge_clearance`/
  `shorting_items` at or below their recorded ceilings) is unaffected by this change and remains
  PASS.
* The `creepage` class and its documented known-finding baseline are unchanged.
* The seed manifest's `_meta.board_sha256` IS re-stamped by this change, via
  `check_board_defect_corpus.py --update-manifest` (the corpus's own documented mechanism, not a
  hand edit) after a green 5/5 run -- the board itself was not touched; only the recorded hash of
  the (unmodified) committed board that had drifted since the 2026-08-04 reseed.
