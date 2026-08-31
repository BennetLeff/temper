<!-- provenance: commit=e5539273a01c030c0968006fcf61bb4bedba65be dirty=UNKNOWN -->
# Board-origin write-path bug: two placement writers wrote normalized coordinates into an absolute-coordinate file

**Found by:** PR #1049 (`feat/board-sync-and-placement`), via
`scripts/check_board_containment.py`. That PR's board itself was rejected
(it discarded all copper — see its closing comment), but this specific
defect is real, independently reproduced, and fixed here
(`feat/board-place-and-reroute`).

## The bug

`parse_kicad_pcb(path, normalize=True)` (the default) subtracts the
board's own Edge.Cuts origin from every parsed component coordinate before
handing it to a caller. For `pcb/temper.kicad_pcb` that origin is
**(20, 20) mm**, not (0, 0):

```
packages/temper-design-bundle/src/parse_engine.rs:1681-1684
    let initial_position = (
        fp.position.x.to_f64() - ox + rotated_cx,
        fp.position.y.to_f64() - oy + rotated_cy,
    );
```

Any CP-SAT solve (OR-Tools or Pumpkin) that runs against this normalized
frame produces positions in the *same* normalized frame. Two production
write-back functions took those positions and wrote them straight into a
template `.kicad_pcb`'s `(at X Y)` fields — which are always in **absolute**
file coordinates — with no reversal:

1. `temper_placer.router_v6._adapter_convert._apply_placements_to_pcb`
   (used by the Pumpkin golden test, `route_pcb`'s internal placement
   write, and this PR's own placement driver).
2. `temper_placer.io._write_board.write_placements_to_pcb` (the `--no-loop`
   CLI's direct CP-SAT write path, `cli/__init__.py`).

Every footprint written by either function landed **~20mm off** toward
(0, 0) relative to the real outline — invisible to the self-consistency
round-trip oracle (`validation.placement_roundtrip.check_placement_roundtrip`),
which re-derives its own "expected" geometry from the same (already-wrong)
positions dict rather than independently from Edge.Cuts, but caught
immediately by `scripts/check_board_containment.py`, which loads the raw
board and outline with no normalization at all.

The pattern already existed correctly elsewhere in the codebase — both
`_loop_routing.py` (`origin_x, origin_y = board.origin; absolute_placements
= {ref: (x + origin_x, y + origin_y) ...}`) and
`io/placement_exporter.py` (`positions_to_placements(..., origin=board_origin)`)
already add the offset back before writing. The CLI's direct `--no-loop`
path and `_apply_placements_to_pcb` were the two call sites that omitted it.

## The fix

Both functions gained a `board_origin: tuple[float, float] = (0.0, 0.0)`
parameter, added to the placement coordinate immediately before it is
written. The default keeps every existing caller byte-for-byte unchanged
(none of them previously passed anything for this position, and none of
them normalized their input) — confirmed by grepping every call site
(`packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`,
`packages/temper-placer/tests/**`) and leaving all but the two production
call sites untouched.

- `_apply_placements_to_pcb(..., board_origin=board.origin)` — this PR's
  own placement driver (see the board-place-and-reroute PR description).
- `write_placements_to_pcb(..., board_origin=board.origin)` —
  `cli/__init__.py`'s `--no-loop` path, `board` already in scope from the
  same `parse_kicad_pcb(input_pcb)` call that produced the normalized
  positions.

Regression tests: `TestApplyPlacementsToPcb::test_board_origin_offsets_written_position`
(`packages/temper-placer/tests/router_v6/test_adapter.py`) and
`TestWritePlacementsToPcbRoundTrip::test_board_origin_adds_offset_and_still_round_trips`
(`packages/temper-placer/tests/io/test_kicad_writer.py`).

## Why the round-trip oracle didn't catch it, and won't catch the inverse mistake either

`check_placement_roundtrip` is a **self-consistency** check: given a
`positions` dict and a written file, it recomputes the pads' expected
world coordinates from `positions` plus each component's own pad-offset
and rotation math, and compares against what the file actually contains.
It never looks at Edge.Cuts. If a caller passes normalized positions to a
writer that fails to add `board_origin`, and then passes those *same*
normalized positions to the oracle, the oracle computes the same wrong
answer twice and reports PASS — this is precisely how the original bug
shipped invisibly. The fix does not change the oracle; it means a caller
that now correctly adds `board_origin` before writing must also pass
`board_origin`-adjusted (absolute) positions to the oracle, not the raw
solver output, or the oracle will report a false FAIL (mismatched by
exactly `board_origin`). `scripts/check_board_containment.py` remains the
only gate that independently anchors to the real outline and would still
catch a *new* regression of this exact class.

## Two related, out-of-scope findings (not fixed here)

- `_apply_placements_to_pcb`'s optional `design_rules=` netclass-block
  insertion (writing legacy `(net_class ...)` s-expressions into the
  `.kicad_pcb`'s `(setup ...)` block) is a dead write against this
  project's real board: KiCad 10 stores netclass rules in
  `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments`, not in the
  `.kicad_pcb` file itself, so nothing reads the inserted block. This PR's
  own placement driver avoids exercising it (`design_rules=None`).
- `packages/temper-placer/temper_constraints.references.yaml` (the legacy
  `temper_induction_cooker.yaml` reference-alias manifest) currently passes
  its own hash-freshness gate, so it is not stale by that metric — several
  of its entries (e.g. `J_AC_IN`, `J_USB`) are permanently unresolvable
  ("no source-backed connector instance") and `loop_aliases: {}` is
  entirely empty. Dead/vacuous content tied to a config
  (`temper_induction_cooker.yaml`) that is itself stale and unsatisfiable
  (see the board-place-and-reroute PR description), not a path or
  reference-drift bug.
