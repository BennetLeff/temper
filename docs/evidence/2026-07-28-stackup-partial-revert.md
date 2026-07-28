# The phantom-layer fix was half right: a 12× routing regression, partially reverted

**Date:** 2026-07-28
**Reverts:** the outer-layer half of `a1fe623e` (merged as `52ccd14c`)
**Retains:** the phantom-`In3.Cu` half of the same commit

## What happened

`a1fe623e` fixed two things in `_extract_stackup()`'s fallback path. One was
right. The other cost **12× routing completion**, and it was merged without the
measurement that would have caught it — the implementing agent stalled before
reaching its own falsifier, and the merge commit said so.

| Change | Verdict |
|---|---|
| `".Cu" in name` → `.endswith(".Cu")`, killing a fabricated `In3.Cu` | **Correct — retained** |
| Force `F.Cu`/`B.Cu` to `signal` before the zone heuristic | **Wrong — reverted** |

## The measurement

Same harness, same board, same commit — only
`packages/temper-placer/src/temper_placer/io/_parse_board.py` differing:

| `_parse_board.py` | completion | unrouted |
|---|---|---|
| pre-`a1fe623e` (phantom `In3.Cu`, outer = plane) | **38.54%** | 59 / 96 |
| post-`a1fe623e` (4 real layers, outer = signal) | **3.12%** | 93 / 96 |
| **this partial revert** (4 real layers, outer = plane) | **38.54%** | 59 / 96 |

The pre-fix figure reproduces the independently-documented 37/96 = 38.5%
baseline exactly, which also validates the harness.

## Why "correct" made it worse

The forced-signal branch was justified by `docs/hardware/POWER_PLANE_DESIGN.md`
and `docs/plans/2026-06-30-001-feat-4-layer-enforcement-plan.md`, both of which
say outer layers are signal and inner layers are GND/PWR planes.

**That is what the design documents say. It is not what the board is.**
`pcb/temper.kicad_pcb` pours per-net copper fill on `F.Cu`/`B.Cu` for creepage
and thermal reasons, so both outer layers are effectively occupied. The old
zone-netname heuristic classified them as planes *because it was reading the
artifact*.

Forcing them to `signal` put two blocked layers into the routing space; layer
assignment spread nets onto them and those nets failed.
`test_astar_3d_production_scale_spike` shows the mechanism directly — its
failure moved from `KeyError: 'F.Cu'` (layer absent) to
`"Could not construct any short same-layer segment for production"` (layer
present, no free cell anywhere on it).

## The generalisable lesson

**The code was "fixed" to match a document instead of the artifact it operates
on.** This is an SSOT-drift instance in its own right: the design intent and the
fabricated board disagree, and nothing flags that. It belongs with the other
drift instances found on 2026-07-27 — Python vs Rust clearance, firmware PLL
constants vs `main.ato`, `drc_ceiling.json` vs the board.

A secondary lesson about process: `a1fe623e`'s root-cause analysis was rigorous
and *proven by direct inspection* — kiutils confirming `setup.stackup is None`,
an `Edge.Cuts` entry satisfying the old substring test. All of that was correct.
It was the **consequence** that went unmeasured. A correct diagnosis does not
imply a safe change.

## What is retained, and why

`.endswith(".Cu")` stays in both places. `In3.Cu` does not exist on this board;
routing copper onto it could not be manufactured. That half of the fix was never
in question, and the partial revert deliberately keeps it — `git revert` of the
whole merge would have discarded it.

## OPEN DESIGN QUESTION (not a code defect)

Should this board's outer layers be poured at all? The documents say outer =
signal; the board pours them. Until that is resolved by a board decision, the
parser follows the board, because the board is what gets routed and DRC'd.

Resolving it toward "outer layers are signal" would require re-pouring the
board, and would then plausibly *raise* routing completion above 38.54% by
returning two real layers to the router — the outcome `a1fe623e` assumed it was
already delivering.

## UNVERIFIED

- **Whether unblocking the outer layers would actually improve completion.** The
  3.12% result shows only that adding *blocked* layers hurts. A board with
  genuinely free outer copper was never measured.
- Via count was not compared across the three configurations; the reference run
  placed zero vias and this harness does not report them.
- The four `test_astar_3d_production_scale_spike` production failures remain.
  They fail for a different reason after this revert than the original
  `KeyError`; not diagnosed here.

## Verification

10/10 gates exit 0; stackup suites 36/36 (`test_stackup_parsing.py`,
`core/test_stackup.py`, `manufacturing/test_stackup_validator.py`);
`elec/validation` 30/30; `make netlist` passes.
