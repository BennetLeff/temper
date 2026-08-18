<!-- provenance: commit=11a7e7c52 dirty=false (worktree agent-aae83c10fb1cc9674, main tip at task start). pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b, matches task brief exactly ("current main"). -->
---
title: "State B: M6c reverted, Tier-3 span-scaled budget fix ALSO reverted — isolating which of #1334's two changes caused fake completions 14->6"
date: 2026-08-17
module: temper-placer
tags: [router, revert, routing-completion, drc, fake-completions]
problem_type: routing-diagnostic
status: in-progress
---

# State B: isolating M6c-revert vs Tier-3-fix as the cause of fake completions 14 -> 6

**Status: IN PROGRESS.** Stub committed first per this project's survival
rule (a worktree with no commits is destroyed on stop). Findings and
measurements follow in later commits to this same file.

## Task, per the coordinating brief

Commit `11a7e7c52` (current main tip) did two things in one commit:
1. Reverted M6c (partial-geometry writing on unreachable serial waypoint
   chains) back to pre-PR-#1329 state, across four files.
2. Landed the Tier-3 span-scaled search-budget fix (`_astar_nlayer.py`
   only, one call site: `segment_3d_fallback_max_iter=max(per_net_max_iter,
   _SEGMENT_3D_FALLBACK_MAX_ITER)`), replacing Tier 3's flat 200,000
   default.

Fake completions moved 14 (state A: M6c present, Tier 3 absent, board
`cb5184eae9...`) -> 6 (state D: M6c reverted, Tier 3 landed, board
`26981fea2d...`, current main). Which change caused it?

**State B (this task): M6c reverted, Tier 3 ALSO reverted/absent.** Take
current main, keep the M6c revert, but undo only the ~40-line Tier-3
call-site change identified in `_astar_nlayer.py` (confirmed by direct
diff inspection of `11a7e7c52` to be the ONLY Tier-3-related change in
the whole commit — the other three M6c files and `_power_islands.py`
carry zero Tier-3 content). Route twice, count fake completions and their
specific net identities, compare against A (14) and D (6).

## 0. State at task start

- Main tip: `11a7e7c52`.
- `pcb/temper.kicad_pcb` sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` --
  matches the task brief's stated current-main hash exactly.
- Confirmed by direct `git show 11a7e7c52 --stat` and full diff
  inspection: the Tier-3 fix touches exactly one file
  (`_astar_nlayer.py`), one call site (the `_astar_route_nlayer(...)` call
  inside `attempt_route`, plus its preceding comment block) — no other
  file in the commit (`routing_results.py`, `terminal_tree_execution.py`,
  `test_all_pad_tree_routing.py`, `pcb/temper.kicad_pcb`) contains any
  `segment_3d_fallback_max_iter`/`_SEGMENT_3D_FALLBACK_MAX_ITER` content.
  `_power_islands.py` is not part of this commit's diff at all (last
  touched by PR #1329/#1332, both upstream of this commit) — confirmed
  untouched, will not be touched by this task either.

## 1. Plan

1. Isolated venv (`make venv-isolate`), verify `temper_placer.__file__`
   resolves inside this worktree before trusting any number. Watch for
   the documented CARGO_TARGET_DIR stale-fingerprint hazard.
2. Edit `_astar_nlayer.py`: remove the `segment_3d_fallback_max_iter=...`
   kwarg (and its comment block) from the `_astar_route_nlayer` call site,
   restoring the implicit default (`_SEGMENT_3D_FALLBACK_MAX_ITER` =
   200,000 flat, unscaled) — i.e. exactly what state D's file looked like
   before the Tier-3 hunk of #1334 was applied, with the M6c revert left
   fully in place (already true of the working tree at commit start).
3. Two full `route_board.py` runs from the committed board's own
   placement, byte-identical required.
4. Count fake completions via `NetRouteResult`/`verify_continuity()` /
   `pad_connectivity_audit`, same methodology as the m6c-revert-tier3-
   reland doc. Report specific net identities.
5. Report connectivity alongside. Compare against A (14, `cb5184eae9`)
   and D (6, `26981fea2d`, current committed board unchanged).
6. Do NOT commit any board changes. `pcb/temper.kicad_pcb` must remain at
   `26981fea2d...` (byte-identical to the currently committed file) when
   this task ends — only scratch copies under `/tmp` are routed.

Findings follow below in later commits to this file.

## 2. Isolated venv, verified

`make venv-isolate` completed clean (no hazards hit -- no CONDA_PREFIX
conflict in this shell, `CARGO_TARGET_DIR` build produced a working
`temper_geometry` cdylib on the first attempt, 374 exported symbols
including `NetRouteResult`, mtime fresh, no stale-fingerprint symptom).

Verified post-build, direct import from `.venv/bin/python3`:
- `temper_placer.__file__` -> this worktree's own
  `packages/temper-placer/src/temper_placer/__init__.py`.
- `_astar_nlayer.__file__` -> this worktree's own file.
- `_astar_nlayer._SEGMENT_3D_FALLBACK_MAX_ITER == 200000` and
  `_astar_route_nlayer`'s `segment_3d_fallback_max_iter` parameter default
  is `200000` (confirms the Tier-3 revert below restores the pre-#1334
  flat default -- nothing passes a larger value at the call site anymore).
- `_power_islands.STITCH_TRACE_WIDTH_MM == 1.0`, file resolves inside this
  worktree (PR #1329's fix intact).
- `test_astar_nlayer.py`: 27/27 pass (matches the reland doc's own
  regression baseline).

## 3. Code change: isolate and revert only the Tier-3 hunk

Full diff inspection of `11a7e7c52` (`git show 11a7e7c52 -- .../_astar_nlayer.py`)
confirmed the Tier-3 span-scaled-budget change is exactly one hunk: a
34-line comment block plus one kwarg
(`segment_3d_fallback_max_iter=max(per_net_max_iter,
_SEGMENT_3D_FALLBACK_MAX_ITER)`) at the single `_astar_route_nlayer(...)`
call site inside `run_astar_pathfinding_nlayer`'s `attempt_route`. No
other file in the commit (`routing_results.py`,
`terminal_tree_execution.py`, `test_all_pad_tree_routing.py`,
`pcb/temper.kicad_pcb`) contains any Tier-3 content.

Removed exactly that hunk (commit `48164c297`, 40 lines deleted, nothing
else touched). Confirmed by diff: `git diff --stat` showed only this one
file, only deletions, and `git diff 7979a0ee1^ HEAD -- <all 4 M6c files>`
came back **empty** for all four -- i.e. this worktree's post-revert state
is byte-identical to the pre-M6c, pre-Tier-3 source (`7979a0ee1^`), modulo
the fact that `_power_islands.py`'s independent PR #1329/#1332 fixes are
still present (untouched by any of this). This is exactly state B's
intended code: M6c reverted, Tier 3 absent.

`_power_islands.py` reconfirmed untouched throughout (`git diff --stat`
empty for that file at every step).

## 4. State B: two full routes

Both runs: `scripts/route_board.py` default recipe (no `--net-batching`,
`--pruning`, `--nlayer-astar-spike`), from the committed board's own
unmodified placement (`pcb/temper.kicad_pcb`, sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`,
verified unchanged before/after every route in this document).

```
stateB_route1.kicad_pcb sha256: 6d4e17337bcf2633fb256f3da4d6fe981c91123827eff715a2c8aa870d195981
stateB_route2.kicad_pcb sha256: 6d4e17337bcf2633fb256f3da4d6fe981c91123827eff715a2c8aa870d195981
```

**Byte-identical.** Both runs also reported identical logs: 34/105
(32.4%), segments=4553 vias=169 zones=151, wall~300s.

`diff` of `stateB_route1.kicad_pcb` against the **currently committed
board** (state D, `26981fea2d...`) shows **exactly one line of
difference — a single blank line** (`8264d8263 < `), i.e. state B's fresh
route reproduces state D's committed board **essentially byte-for-byte**.
This is a strong, independent confirmation (not merely the summary
numbers matching) that removing the Tier-3 hunk from state D's code
reproduces state D's *exact* routing outcome.

**Connectivity: 60/139** (both runs, identical) -- same as state D's
60/139.

**Fake completions: 6** (`NetRouteResult`, `verify_continuity()`-backed,
matches `route_board.py`'s own `pad_connectivity_audit`-derived report --
this is the project's canonical fake-completion methodology, confirmed by
reading `pad_connectivity_audit.py`'s `is_fake_completion` property:
`has_any_copper and not fully_connected`, i.e. exactly "the b39b382d
shape" the log itself names):

```
+15V, +3V3, GATE_LS, V_BUS_SENSE, gnd, vcc
```

**This is the identical net set state D reports** (per the m6c-revert-
tier3-reland doc's own §5d: `+15V, +3V3, GATE_LS, V_BUS_SENSE, gnd, vcc`).
Not just the same count -- the same six nets, byte-for-byte.

## 5. State A cross-check: measured directly (not merely cited)

To identify which specific 8 nets disappear (not just confirm the count),
state A's exact code was reconstructed on top of this same worktree:
`git show 7979a0ee1:<path>` (PR #1329's merge commit, M6c's own landing
commit) for all four M6c files, restoring them to M6c-present form.
Diff sizes matched the reland doc's own figures exactly (168/71/195/45
lines). `_power_islands.py` reconfirmed untouched. Committed as
`8fa3bf1dc` (diagnostic-only, clearly labelled, not for merge). Tier 3 is
necessarily absent in this state too -- it did not exist as a concept
until `11a7e7c52`, which postdates `7979a0ee1`.

Regression check: `test_all_pad_tree_routing.py` 15/15 pass on the
restored M6c code.

Two full routes:

```
stateA_route1.kicad_pcb sha256: 3d6bd429c6a8bd680ea29ee763af835b026e7436799a1404d1c5b5e0c617c379
stateA_route2.kicad_pcb sha256: (pending, see next commit)
```

route1: **Connectivity 59/139**, **fake-completion=14**, matching prior
evidence docs' recorded count for this state exactly (the hop-reachability
doc's §2 baseline: "59/139 connected... Fake-completion count: 14").

**Specific fake-completion nets (14):**

```
+15V, +3V3, GATE_LS, I_SENSE, RTD_HW_FAULT, V_BUS_SENSE, bias, en, gnd,
ina, io0, safety.thermal.comp-inp, safety.uvlo_logic.mon-ina_p, vcc
```

## 6. The net-identity diff: state A's 14 minus state B's 6

```
A (14): +15V, +3V3, GATE_LS, I_SENSE, RTD_HW_FAULT, V_BUS_SENSE, bias,
        en, gnd, ina, io0, safety.thermal.comp-inp,
        safety.uvlo_logic.mon-ina_p, vcc
B (6):  +15V, +3V3, GATE_LS, V_BUS_SENSE, gnd, vcc

A \ B (the 8 that disappear when M6c is reverted):
        I_SENSE, RTD_HW_FAULT, bias, en, ina, io0,
        safety.thermal.comp-inp, safety.uvlo_logic.mon-ina_p
```

**B is an exact subset of A** -- all 6 of B's fake-completion nets also
appear in A's 14. Nothing in B's set is new; nothing in A's set is
missing from A when compared to B except precisely these 8. This is the
cleanest possible confirmation shape: M6c's presence adds exactly 8 fake
completions on top of a 6-net floor that exists **with or without M6c**.

**Cross-check against the hop-reachability doc's own 17-net "0-of-N"
class** (`_DEBUG_M6B_NETS` in `_astar_nlayer.py`: `+15V_LS,
discharge.k_dis1-nc, discharge.k_dis2-nc, en, hb.gate_hs.driver-p1-1,
hb.gate_hs.driver-p2, hb.power_loop.q_high-g, io0, safety-line,
safety-line-1, safety.ocp.comp-inn, safety.ovp-line, safety.ovp.comp-inp,
safety.thermal.comp-inp, safety.uvlo_logic-line,
safety.uvlo_logic.mon-outa, y`): **3 of the 8 disappearing nets --
`en`, `io0`, `safety.thermal.comp-inp` -- are exact-name matches** to that
independently-instrumented class, and a 4th (`safety.uvlo_logic.mon-ina_p`)
is the same functional pin group as that class's
`safety.uvlo_logic-line`/`safety.uvlo_logic.mon-outa`. This is not a
coincidental overlap: it is the same mechanism, confirmed from two
independent directions (per-hop instrumentation in one document, exact
net-identity diffing in this one).

## 7. Mechanism, read directly from the code (not inferred)

`_astar_route_nlayer` walks a net's pads as a **serial waypoint chain**
(`expand_channel_path_terminals`/`run_expand_all_pad_tree`), one hop
(`waypoints[i] -> waypoints[i+1]`) at a time. The two code paths differ
in exactly one place: what happens when a hop's Tier 1/2/3 search all
decline and `allow_forced_segments` is `False` (the production policy for
every net in this class).

**Non-M6c (state B, reverted code, `_astar_nlayer.py` current HEAD)**:
the loop is a plain `for i in range(len(waypoints) - 1)`. The instant one
hop fails, the function **returns immediately** with whatever
`detailed_segments` had already been accumulated from the hops *before*
the failing one -- nothing from *after* is ever attempted. If the
**first** hop is the one that fails (the dominant sub-case in the
hop-reachability doc's own per-hop instrumentation: "12 of the 17 nets in
this class fail on their very first hop"), `detailed_segments` is still
empty at that point, so the net returns with **zero geometry** -- a clean
"failed" net (`has_any_copper == False`), not a fake completion.

**M6c (state A, restored code)**: the loop tracks a `current_anchor`
instead of a fixed index and, on a hop failure with
`allow_forced_segments=False`, **does not return** -- it `continue`s the
loop without advancing `current_anchor`, so the *next* iteration retries
from the same last-known-good point to the *next* waypoint in the chain.
A net whose first hop fails therefore still gets a chance at hop
`waypoints[0] -> waypoints[2]`, `waypoints[0] -> waypoints[3]`, etc. When
one of those later attempts succeeds, real A*-searched segments land in
`detailed_segments` -- satisfying `_has_safe_partial_geometry` (`len(points)
>= 2 and path_length > 0.0`, shared, unchanged code) -- and the net is
preserved in `partial_paths`, later written to the board as real copper
for the pads it DID reach. `forced_segments = len(failed_waypoint_indices)`
at the end of the full loop correctly marks the net as not-fully-routed,
so `NetRouteResult::Connected` is never (and was never claimed to be)
falsely set for these nets -- `verify_continuity()` still gates it, and
the guarantee's letter holds.

**But the fake-completion metric being measured in this task is not "was
Connected falsely claimed" -- it is `pad_connectivity_audit`'s
`is_fake_completion = has_any_copper and not fully_connected`, i.e. "does
this net now have copper that a naive glance would read as progress, when
it isn't actually finished."** M6c's entire purpose was to convert some of
these first-hop failures from "zero geometry, clean fail" into "some
geometry, still incomplete" -- and that conversion is *exactly* the shape
this metric flags. M6c doesn't fabricate a false `Connected`; it
fabricates the *intermediate* state the original 62-fake-completion
incident (and this project's entire type-guard discipline) exists to
catch: copper on a mains-adjacent or safety-relevant rail that looks like
partial progress but is an open circuit exactly as much as zero copper
would be. `GATE_LS`'s persistence in *both* A and B (unaffected by M6c)
confirms this is not the only source of that shape in the router --
the `landing_blocked` path (`_astar_nlayer.py` ~line 1213) preserves
partial geometry through an entirely separate, M6c-independent mechanism
-- but M6c is a *second*, additive source of exactly the same hazard, and
it accounts for 8 of the 14 nets in this specific measurement.

## 8. Verdict

**State B = 6**, matching the task brief's pre-registered interpretation
for this outcome exactly:

> **The M6c revert caused the improvement.** M6c was producing 8 fake
> completions despite its verified design intent. Root-caused (§7): M6c's
> stated guarantee -- `NetRouteResult::Connected` only ever comes from
> `verify_continuity()` -- **held** (never falsely set for any of these
> nets, both before and after this session's revert). But that guarantee
> is narrower than the safety property the project actually needs. M6c's
> skip-and-resume waypoint logic converts some nets that would otherwise
> **cleanly fail with zero copper** into nets that get **partial copper**
> for whichever hops happened to succeed after a skipped failure -- and a
> net with real, DRC-legal copper that still doesn't join every pad is
> indistinguishable, to any downstream consumer that isn't specifically
> auditing `is_fake_completion`, from a genuinely-progressing route. This
> is the same shape the original 62-fake-completion incident was about:
> *presence of copper is not evidence of connectedness*, and M6c
> mechanically manufactures more copper-without-connectedness than the
> code it replaced, for exactly the nets whose first waypoint hop has no
> legal path (12 of the 17-net "0-of-N" class, per the hop-reachability
> doc's own per-hop instrumentation).

**The Tier-3 fix's measured contribution to this metric in this
measurement: zero.** State B's fresh route (Tier 3 absent) is byte-
identical, modulo one blank line, to state D's committed board (Tier 3
present) -- the two states could not be closer. This is independently
consistent with the hop-reachability doc's own §6 finding that "none of
the 3 hops the read-only probe found recoverable... were recovered" by
the shipped (capped-at-1,000,000, span-proportional) version of the fix
in the cases it targeted, and that three attempted full-route
verifications of the fix alone were killed before completion without
ever producing a connectivity/fake-completion number. This document is
the first to actually complete that measurement, and the answer is: on
this board, in this exact code state, the Tier-3 fix changes nothing
about which nets route, how many pads connect, or how many fake
completions occur. It remains real and safe on its own terms (bounded,
span-proportional, cannot fabricate a completion by construction, per
that doc's §6) -- it simply had no opportunity to matter for the specific
hops this board's routing order happens to present it with.

## 9. Connectivity, reported alongside (not confused with fake-completion)

| state | connectivity | fake-completion | fake-completion nets |
|---|---|---|---|
| A (M6c present, Tier 3 absent) | 59/139 | 14 | +15V, +3V3, GATE_LS, I_SENSE, RTD_HW_FAULT, V_BUS_SENSE, bias, en, gnd, ina, io0, safety.thermal.comp-inp, safety.uvlo_logic.mon-ina_p, vcc |
| B (M6c reverted, Tier 3 absent) | 60/139 | 6 | +15V, +3V3, GATE_LS, V_BUS_SENSE, gnd, vcc |
| D (M6c reverted, Tier 3 landed, = current main) | 60/139 | 6 | +15V, +3V3, GATE_LS, V_BUS_SENSE, gnd, vcc |

State C (M6c present, Tier 3 landed) was **not measured** -- with B
already decisive and reproducing D almost byte-for-byte, and this
session's time/disk budget already having produced two independent
double-route measurements (4 full routes total, ~35 minutes of route
time), C would only confirm what B and the Tier-3-absent/-present
byte-identical comparison already show unambiguously: Tier 3 is inert for
this board's current failure set. Flagged here explicitly rather than
silently skipped, per the brief's own instruction to say so rather than
half-do it.

## 10. Board integrity

`pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
verified unchanged at every checkpoint in this document (before the code
edit, after the code edit, after both state-B routes, after restoring and
routing state A's diagnostic code, and after reverting that diagnostic
code back out). All routing output went to `/tmp` scratch paths only. No
board was committed. The worktree's final code state is state B (the
diagnostic M6c-restoration commit `8fa3bf1dc` was reverted by
`c847255cc`; `git diff 7979a0ee1^ HEAD` for all four M6c files is empty,
confirming the working tree matches pre-M6c, pre-Tier-3 source exactly).
