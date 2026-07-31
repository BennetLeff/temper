---
title: "One small pour deletes an entire copper layer from the router — a fix that corrected the predicate left the quantifier bug alive"
date: "2026-07-29"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: routing
severity: critical
symptoms:
  - "F.Cu and B.Cu both classify as layer_type='plane' even though only 4 of 48 zones on each is on a plane-required net"
  - "routing_space.py:85 drops every layer whose layer_type is not 'signal'/'mixed' from compute_routing_space()'s output -- both outer copper layers vanish from the router's routing space entirely"
  - "via count is structurally pinned at 0 (vias need at least two routable layers to transition between; only the inner layers remained)"
  - "the previous day's fix to _is_plane_required_net (merge 27368038) corrected which nets trigger plane classification but did not change how many zones it takes to condemn a layer"
root_cause: "_extract_stackup() (packages/temper-placer/src/temper_placer/io/_parse_board.py:198-210, 236-252) marks a whole physical copper layer layer_type='plane' if hasattr(zone, 'layers') and _is_plane_required_net(zone.netName) is True for ANY zone on that layer -- the existential quantifier over zones is unconditional. routing_space.py:85 (`if layer_info.layer_type not in [\"signal\", \"mixed\"]: continue`) then excludes any non-signal/mixed layer from the routing space wholesale. On the production board only 4 of 48 zones per outer layer (ac_l, ac_n, DC_BUS_RTN, SW_NODE) are plane-required, but that is sufficient to condemn the entire physical layer, not just the area those 4 zones occupy."
resolution_type: opt-in_fix
tags:
  - stackup-classification
  - plane-required-net
  - existential-quantifier-bug
  - predicate-vs-quantifier
  - routing-space-exclusion
  - opt-in-flag
related_components:
  - temper_placer.io._parse_board
  - temper_placer.router_v6.routing_space
  - temper_placer.router_v6.obstacle_map
---

# One small pour can delete an entire copper layer from the router

## Problem

`_extract_stackup()` in
`packages/temper-placer/src/temper_placer/io/_parse_board.py` classifies a
physical copper layer's `layer_type` as `"plane"` whenever **any** zone on
that layer sits on a plane-required net (`_is_plane_required_net`, lines
198-210 for the zone scan, lines 236-252 for the layer-role assignment).
`routing_space.py:85` then excludes any layer whose `layer_type` is not
`"signal"` or `"mixed"` from `compute_routing_space()`'s output entirely —
not just the area the plane-required pour occupies, the whole layer.

On the production board (`pcb/temper.kicad_pcb`), F.Cu carries 48 zones,
of which only 4 (`ac_l`, `ac_n`, `DC_BUS_RTN`, `SW_NODE`) are plane-required.
The other 44 are ordinary signal-net pours. Because the check is "does at
least one plane-required zone exist on this layer" rather than "how much of
this layer's area is plane-required," those 4 zones were enough to condemn
the whole layer — F.Cu and B.Cu were both completely absent from
`compute_routing_space()`'s output, halving the board's usable copper and
structurally pinning the via count at 0 (a via needs at least two routable
layers to transition between, and only the inner layers remained).

## The sharp part

The day before this was found, merge `27368038`
("fix(placer): stop a one-char substring match and a hardcoded netclass
list from misclassifying planes") replaced a bare `"+" in zone.netName`
substring test with `_is_plane_required_net`, a real net-classification
lookup (`TEMPER_NET_CLASSES[nc].routing_strategy == "plane_required"`, with a
word-boundary-anchored keyword fallback). That fix was correct and
necessary — the old substring test misclassified nets like `+3V3` — but it
answers a different question than the one that was actually costing the
board its outer layers. **`_is_plane_required_net` decides which nets count
as plane-worthy (the predicate). Nothing about fixing it touches the
separate question of how many such zones on a layer are enough to condemn
the whole layer (the quantifier).** Both bugs live in the same function,
adjacent to each other, and fixing one left the other's symptom — F.Cu/B.Cu
absent from routing — completely unchanged, because the predicate was never
where the quantifier bug lived.

**A fix that corrects the predicate but not the quantifier leaves the bug
alive.** Confirming `_is_plane_required_net(zone.netName)` returns the
right boolean for every zone says nothing about what the calling code does
with that boolean once it's `True` for even one zone out of 48.

## Solution (opt-in, fixed in commit `20dd3533`)

`_extract_stackup()` and `parse_kicad_pcb_v6()` gained
`use_declared_layer_roles: bool = False`. When `True`, `layer_type` comes
from a layer's structural position in the declared stackup (index 0 and the
last copper index are `"signal"`; everything between is `"mixed"`) and is
never overridden by zone content — `plane_net` is still populated from the
zone scan for callers that want to know "does a plane-required pour sit
here," but that fact no longer decides routability.

```python
# packages/temper-placer/src/temper_placer/io/_parse_board.py:236-243
if use_declared_layer_roles:
    # R8: role comes from the stackup declaration -- structural
    # position among this board's declared copper layers -- not
    # from zone content. plane_net is still surfaced when a
    # plane-required zone sits here, but it no longer decides
    # layer_type.
    layer_type = "signal" if i == 0 or i == layer_count - 1 else "mixed"
    plane_net = plane_assignments.get(name)
elif name in plane_assignments:
    layer_type = "plane"
    plane_net = plane_assignments[name]
```

The flag defaults `False` — today's behavior is unchanged — and its own
docstring records why it is not yet safe to flip on in production:
`obstacle_map.py` still unions every zone on a layer into an opaque
obstacle regardless of net (see
`docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`'s
extension for the traced mechanism), so opening the outer layers without
first making pours derived output hands the router two mostly-blocked
layers instead of two usable ones — reproducing the recorded 12x completion
regression rather than fixing anything. This flag's flip to `True` must land
in the same change as the pours-become-derived-output work.

## Why This Matters

The predicate/quantifier distinction generalizes past this one function:
"is X true of this item" and "how many items need X to be true before I act
on the whole collection" are independent design decisions, and a bug report
that reproduces after a predicate fix is evidence the quantifier was never
touched — not evidence the predicate fix was wrong. Here, four zones out of
forty-eight — 8% of the layer's pours — were sufficient to remove 100% of
the layer from the router's routing space. That ratio (a handful of
legitimate small pours condemning an entire physical layer) is the signature
of a quantifier bug: the fix scales with "does at least one exist," not with
how much of the layer the plane-required content actually occupies.

## Prevention

- **When a classifier's fix report says "corrected which items match X,"
  separately ask "and how many matching items does the consumer require
  before it acts on the whole collection?"** These are answerable
  independently and a fix to one does not imply anything about the other.
- **An `any(...)` or "if hasattr and predicate(item)" check inside a loop
  that sets one classification for an entire collection is the AST shape to
  grep for.** `_extract_stackup`'s zone loop sets `plane_assignments[layer]`
  the first time any zone on that layer satisfies the predicate — the loop
  never counts, never measures area, never asks "how much."
- **Ship a structural fix behind an opt-in flag with its unlock condition
  documented in the same docstring**, exactly as `use_declared_layer_roles`
  does — a fix for the classification half of a two-part bug that is not
  yet safe to enable alone should say so at the point someone will next
  consider flipping the flag, not just in a separate evidence document.

## Related

- `docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
  — the sibling incident in the same function: forcing outer layers to
  `"signal"` (rather than fixing the plane-condemnation quantifier) caused a
  12x routing-completion regression; see its 2026-07-29 extension for the
  `obstacle_map.py` mechanism this doc's fix must land alongside before the
  opt-in flag is safe to default on.
- `docs/evidence/2026-07-28-stackup-partial-revert.md` — the measurement
  table (38.54% vs 3.12% vs 38.54% completion) for the related forced-signal
  regression.
- `packages/temper-placer/src/temper_placer/io/_parse_board.py:130-148` —
  `_is_plane_required_net`, the predicate fixed the day before (merge
  `27368038`) without touching the quantifier bug this doc addresses.
- `packages/temper-placer/src/temper_placer/router_v6/routing_space.py:85`
  — where a condemned layer's exclusion actually takes effect.
- Commit `27368038` — the predicate fix (which nets count as plane-required).
- Commit `20dd3533` — the quantifier fix (`use_declared_layer_roles`,
  opt-in, default off).
