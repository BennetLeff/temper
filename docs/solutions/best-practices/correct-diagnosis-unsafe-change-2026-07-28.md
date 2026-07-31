---
title: "A correct diagnosis does not imply a safe change — the phantom-layer fix that cost 12× routing completion"
date: "2026-07-28"
category: best-practices
module: temper_placer
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a root-cause analysis is rigorously proven (direct library inspection, a passing regression test, a cited design document) before its fix is merged"
  - "a fix aligns the code with what a design document says rather than with what the artifact the code operates on actually is"
  - "a bug-fix PR changes classification/parsing logic and the before/after measurement on the real artifact was not run before merge"
  - "reviewing a merge commit whose message reports the implementing agent 'stalled before reaching its own falsifier'"
tags:
  - correct-fix-wrong-consequence
  - measure-before-merge
  - stackup-parsing
  - ssot-drift
  - routing-regression
  - doc-vs-artifact
---

# A correct diagnosis does not imply a safe change

## Context

`_parse_board.py`'s `_extract_stackup()` fallback path had two problems,
fixed together in one commit (`a1fe623e`, merged as `52ccd14c`):

1. `".Cu" in name"` matched `Edge.Cuts` as a copper layer, fabricating a
   nonexistent `In3.Cu` on a board that has no such physical layer.
   Fixed by `.endswith(".Cu")`.
2. The fix's author, reasoning from `docs/hardware/POWER_PLANE_DESIGN.md`
   and `docs/plans/2026-06-30-001-feat-4-layer-enforcement-plan.md` — both
   of which state outer layers are signal and inner layers are GND/PWR
   planes — additionally forced `F.Cu`/`B.Cu` to `"signal"` before the
   existing zone-netname heuristic ran.

Both changes were **individually well-reasoned and independently
verified**: the phantom-`In3.Cu` diagnosis was confirmed by direct
`kiutils` inspection (`board.setup.stackup is None`), and the `Edge.Cuts`
entry was shown to satisfy the old, buggy substring test exactly as
predicted. The forced-signal branch cited two real design documents that
say, unambiguously, what the stackup is supposed to be. Every step of the
reasoning was correct.

**The consequence was not measured before merge, and it was severe.**
Re-running the harness with only `_parse_board.py` differing:

| `_parse_board.py` state | completion | unrouted |
|---|---:|---:|
| pre-fix (phantom `In3.Cu`, outer layers = plane) | **38.54%** | 59/96 |
| post-fix (4 real layers, outer layers forced = signal) | **3.12%** | 93/96 |
| partial revert (4 real layers, outer layers = plane) | **38.54%** | 59/96 |

Forcing the outer layers to `"signal"` put two **blocked** layers into
the router's routing space: `pcb/temper.kicad_pcb` pours per-net copper
fill on `F.Cu`/`B.Cu` for creepage and thermal reasons, so both outer
layers are, in fact, occupied, regardless of what the design documents
say they should be. `test_astar_3d_production_scale_spike`'s own failure
mode shows the mechanism directly: it moved from `KeyError: 'F.Cu'`
(layer absent from the model) to `"Could not construct any short
same-layer segment for production"` (layer present in the model, no
actually-free cell anywhere on it). The layer went from missing to
present-but-unroutable, and completion dropped 12×.

The merge commit message for `a1fe623e` itself recorded that the
implementing agent had stalled before reaching its own stated falsifier —
the measurement that would have caught this was specified, and not run,
before the change landed.

`docs/evidence/2026-07-28-stackup-partial-revert.md` reverted only the
forced-`"signal"` half and kept the `.endswith(".Cu")` half, restoring
38.54% while keeping the part of the fix that was never in question (a
nonexistent layer cannot be manufactured or routed onto, regardless of
what any document says).

## The pattern

**A correct diagnosis is a claim about the past state of the code; a safe
change is a claim about the future state of the system the code drives.
Proving the first proves nothing about the second.** The phantom-`In3.Cu`
diagnosis and the forced-signal diagnosis were both true statements about
what the code currently did wrong. Whether fixing either one would
*improve* the system's actual measured behavior is a completely separate
question, answerable only by running the same measurement before and
after — and it was answered for neither half before merge.

The forced-signal half is additionally an SSOT-drift instance in its own
right, structurally identical to the substring-classification and
net-name-as-claim incidents this project has already documented, but at
one further remove: **the code was fixed to match a document instead of
the artifact the document describes.** `POWER_PLANE_DESIGN.md` says outer
layers are signal; the board, as actually fabricated in
`pcb/temper.kicad_pcb`, pours them. The old zone-netname heuristic
classified them as `"plane"` *because it was reading the real artifact* —
it was accidentally right for a reason nobody had verified, and "fixing"
it to match the aspirational document made it wrong for a reason that
looked, from inside the diagnosis, like correctness.

## Guidance

1. **A rigorous diagnosis is a precondition for a safe fix, not a
   substitute for measuring one.** Direct library inspection, a
   regression test confirming the bug reproduces, and a cited source
   document are all genuine evidence that a diagnosis is correct. None of
   them are evidence about what happens to the system's behavior once the
   fix is applied — that requires actually running the system, before and
   after, on the same input.
2. **When a fix's justification is "the code should match this document,"
   check the document against the artifact first, not just against the
   code.** A design document and a fabricated board can disagree, and when
   they do, the artifact that gets routed and DRC'd is the one that
   matters operationally — not the one with the more authoritative-looking
   citation. This generalizes
   `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
   from a net's name to a design document's stated intent: both are
   documentation, and neither is automatically true of the artifact.
3. **Before merging any change to classification, parsing, or
   stackup/layer-detection logic, run the project's own standard
   completion/regression measurement and compare before/after on the
   unmodified real artifact.** This is cheap relative to the cost of
   discovering a regression after merge, and it is exactly the falsifier
   this incident's own merge commit recorded as unreached.
4. **A merge commit that reports its own falsifier as unreached is a stop
   sign, not a footnote.** If an agent (or engineer) states up front what
   measurement would confirm a fix is safe, and the commit lands before
   that measurement runs, treat the change as unverified regardless of how
   sound the diagnosis reads — the diagnosis and the verification are
   different questions with different evidence.
5. **When reverting, revert only the half that caused the regression, not
   the whole commit.** The partial revert here kept `.endswith(".Cu")`
   (never in question — `In3.Cu` cannot be manufactured, full stop) and
   reverted only the forced-signal branch. A blanket `git revert` of the
   whole merge would have restored the phantom-layer bug to fix a
   regression the phantom-layer fix never caused.
6. **An unresolved design/artifact disagreement is a decision to make, not
   a default to assume.** Whether this board's outer layers *should* be
   poured is still open — resolving it toward "outer = signal" would
   require re-pouring the board first, and would then plausibly raise
   completion above 38.54% by returning two genuinely free layers to the
   router, which is the outcome the original fix assumed it was already
   delivering. Until that decision is made and the board is actually
   changed, the parser follows the board, because the board is what gets
   routed and DRC'd.

## Why This Matters

Every individual step in this incident was correct: the `In3.Cu`
fabrication was real and was diagnosed correctly; the design documents do
say outer layers are signal; the fix that followed from citing them is a
textbook "match the spec" change. None of that prevented a 12×
regression, because "correct" was being evaluated against the wrong
referent — a document about what the board should be, rather than the
board `pcb/temper.kicad_pcb` actually is. A team that treats "the
diagnosis was rigorous" as sufficient grounds to merge will keep making
this exact mistake, because rigor and safety are answers to different
questions, and only one of the two questions was asked here before merge.

## When to Apply

- Before merging any fix to layer classification, net classification, or
  stackup parsing — run the project's completion/regression harness
  before and after on the unmodified real artifact, not a synthetic
  fixture.
- When a fix's stated justification cites a design document rather than
  the artifact the code operates on — check the document against the
  artifact first; they can, and here did, disagree.
- When a diagnosis is proven by direct inspection (a debugger, a library
  call, a reproduction) but the fix has not yet been measured
  end-to-end — treat the diagnosis and the fix's safety as two separate,
  independently-required proofs.
- When reviewing a merge commit that names its own falsifier as
  unreached — do not treat the commit as done; treat the falsifier as
  still owed.
- When reverting a regression — isolate which half of a multi-part fix
  caused it before reverting, rather than reverting the whole change.

## Examples

```python
# a1fe623e -- both changes landed in one commit, only one caused a regression

# Change 1 (retained, correct, and safe): kills a fabricated layer.
# WRONG (pre-fix):
is_copper = ".Cu" in name          # "Edge.Cuts" contains ".Cu" -> phantom In3.Cu
# RIGHT (the fix, unchanged by the later partial revert):
is_copper = name.endswith(".Cu")

# Change 2 (reverted): "corrects" the artifact to match a document.
# WRONG (the regression):
if layer in ("F.Cu", "B.Cu"):
    layer_type = "signal"          # per POWER_PLANE_DESIGN.md -- but the
                                    # board actually pours copper here
# RIGHT (partial revert): let the existing zone-netname heuristic classify
# outer layers from what the board's own zones actually say, the same way
# it always did for inner layers.
```

```
# The measurement that would have caught this before merge (never run
# before a1fe623e landed):
route_pcb(pcb_before_fix)  -> 38.54% completion
route_pcb(pcb_after_fix)   ->  3.12% completion   # <- stop here, don't merge
```

## Related

- `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
  — the sibling lesson this generalizes: a net's declared name outranking
  its actual topology is the same shape as a design document outranking
  the artifact it describes.
- `docs/solutions/best-practices/substring-net-classification-drifts-from-ssot-2026-07-27.md`
  — the `.Cu`-substring half of this same bug is exactly the defect class
  that doc's gate exists to catch; see its 2026-07-28 update for the
  sibling instance found in the same code area.
- `docs/solutions/best-practices/benchmark-before-optimizing-state-the-falsifier-2026-07-26.md`
  — a sibling incident on the same theme, item 4: "correct in principle"
  is not "safe to land," there for a performance restructuring rather
  than a classification fix.
- `docs/evidence/2026-07-28-stackup-partial-revert.md` — the full
  measurement table, the mechanism trace through
  `test_astar_3d_production_scale_spike`'s changed failure mode, and the
  still-open design question about whether the outer layers should be
  poured at all.
- `packages/temper-placer/src/temper_placer/io/_parse_board.py:264-272` —
  the retained fix and the reverted branch, in place today.

---

## An update, 2026-07-29: the regression's mechanism, traced to source

This document's original text left the *why* unresolved beyond "forcing the
outer layers to `signal` put two blocked layers into the routing space."
The specific mechanism inside the router that makes an outer layer
`blocked` — as opposed to merely present but empty — is
`packages/temper-placer/src/temper_placer/router_v6/obstacle_map.py:94-123`.
Its zone-handling loop unions **every** zone on a layer into that layer's
obstacle polygon, regardless of which net the zone belongs to, under an
explicit comment:

```python
# packages/temper-placer/src/temper_placer/router_v6/obstacle_map.py:123
# Safe default: Treat as obstacle. The router connects to PADS, not zones directly yet.
layer_obstacles[layer].append(poly)
```

`routing_space.py` then subtracts the unioned obstacle polygon from the
board outline (`available_area = board_polygon.difference(obstacles)`) to
produce the routable region for that layer. Forcing F.Cu/B.Cu to
`"signal"` (the reverted half of `a1fe623e`) made `routing_space.py:85`'s
layer-type filter stop excluding those two layers wholesale — but every
pour already on them, `HighVoltage`-class and ordinary alike, was still
unioned into the obstacle polygon by `obstacle_map.py`'s net-blind zone
loop. The outer layers went from *absent* (filtered out entirely) to
*present but mostly obstacle* — measured at roughly 24.7% available area on
F.Cu versus roughly 98% on the inner layers for the same board. Opening a
layer without first making its pours derived output (rather than the
board's existing, un-regenerated zones) hands the router two layers it can
see but can barely use, which is a worse starting point for layer
assignment than not seeing them at all: nets get assigned to F.Cu/B.Cu on
the assumption that "present in the routing space" means "routable," fail
to find any free cell, and contribute to exactly the 12x completion drop
this document already measured. This is also why `use_declared_layer_roles`
(see
`docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md`)
must not be flipped on in production before pours become derived output —
its own docstring names this document by name as the reason.

**A methodology note, worth recording alongside the mechanism itself.**
The first attempt to find this mechanism concluded the opposite of the
truth — that zone content was *invisible* to the obstacle map, not that it
was unconditionally treated as opaque — because `grep zone
stage2_orchestrator.py` returned nothing. That grep was accurate about its
literal target: `stage2_orchestrator.py` itself never mentions zones by
name. But the file that matters is not the one with no hits; it is the one
`stage2_orchestrator.py` **imports and runs** — `ObstacleMapStage`, imported
at line 21 and instantiated in the stage list at line 36
(`from temper_placer.router_v6.obstacle_map import ObstacleMapStage`, ...
`ObstacleMapStage(),`). The zone-handling logic lives inside that imported
stage's own module, not in the orchestrator that merely sequences it.
**Grepping one file for a keyword is not evidence of absence when the
behavior in question is composed from a stage pipeline** — the correct
search target is every module a suspected orchestrator delegates to, not
the orchestrator's own source text. The same mistake, made about a
different pipeline stage, would produce the identical false "not handled
here" conclusion for the same reason: the orchestrator's job is to
sequence stages by name, not to contain the logic those names refer to.

**Related to this update specifically:**
`docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md`
— the sibling logic error in the same code area (a single plane-required
zone condemning a layer's *classification*, independent of this document's
regression, which is about the obstacle map's *geometry* once a layer is
already open); `packages/temper-placer/src/temper_placer/router_v6/obstacle_map.py:94-123`
and `stage2_orchestrator.py:21,36` — the traced mechanism and its import
site.
