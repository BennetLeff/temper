# Clearance (16/666) and copper_balance (4 unbalanced layers) investigation

<!-- provenance: commit=02e907b9d19eab77a13cb63a390af18b1c1d7d10 dirty=true (work commit; base per task instructions) -->

**Date:** 2026-07-27

**Scope:** the two manufacturing-DRC defect classes `docs/evidence/
2026-07-27-drc-checks-repaired.md` left untouched: `clearance` (Rust
backend, 16/666, "unaffected by this task") and `copper_balance` (4
unbalanced layers, `total_area_mm2=35,568` flagged UNVERIFIED/implausible
by that doc and the earlier `docs/evidence/2026-07-27-committed-route.md`).

**FALSIFIER, stated up front:** *"The 16 clearance violations and 4
copper-balance violations are real, durable defects. If the copper area is
miscomputed, or if most clearance violations are routing artifacts of an
incomplete route, then the honest deliverable is those findings -- a
corrected measurement and a smaller true defect count -- not a reduced
violation number."*

**Verdict: the falsifier partially fires, in an unexpected direction.**
The `total_area_mm2` figure is **not** miscomputed -- it is the board's
actual physical area, confirmed independently three separate ways (below).
But `copper_balance`'s *per-layer* area computation is confirmed broken by
a different, more consequential mechanism than the one the task
hypothesized (not double-counting, not units, not bbox-summation): it is
**structurally blind to all zone-pour copper** (documented in the check's
own docstring, never previously stress-tested against a board that
actually uses zone pours for planes -- this board does, extensively). The
4-unbalanced-layer *verdict* happens to survive the correction (see Part A
Sec 3), but the check's own numbers are off by roughly 4-5x on the layers
that have real pour copper, and the check would silently misreport a
*real* balanced layer as unbalanced (or vice versa) on any board where the
true coverage sits near the 30-70% band. This is a "Missing" class defect
per METHODOLOGY.md Sec 4 (the check exists, runs, and never crashes -- it
just cannot see most of what it is supposed to measure), not a "Wrong"
one. For clearance, a **different**, previously-undiscovered "Missing"
defect was found and fixed (tree-routed nets were entirely invisible to
the check -- see Part B Sec 1) but it is currently dormant on this board
(0/4 sampled live-route runs used tree routing), so it does not change the
reported 16/666. The 16 violations themselves are then classified by
origin (Part B Sec 2-3).

---

## PART A -- the 35,568 mm² figure

### A.1 Board's actual physical area, derived from `pcb/temper.kicad_pcb`

The committed board's `Edge.Cuts` outline (single `gr_poly`, `pcb/
temper.kicad_pcb:8202-8208`):

```
(gr_poly (pts (xy 20 20) (xy 172 20) (xy 172 254) (xy 20 254))
  (layer "Edge.Cuts") (width 0.1))
```

Bounding box: **152 mm x 234 mm = 35,568 mm²** exactly (`152 * 234 =
35568`). This is not a new measurement -- it is independently corroborated
by five prior evidence docs already in the repo (`docs/STRATEGY.md:158`,
`docs/evidence/2026-07-26-bus-capacitor-architecture-review.md:31`,
`docs/evidence/2026-07-27-clearance-resolve-full-coverage.md:110`,
`docs/evidence/2026-07-27-domain-clearance-constraint.md:363`, `docs/
evidence/2026-07-27-placement-resolve-after-0805.md:83,161`), all citing
the same 152x234mm outline for unrelated reasons (placement feasibility,
not copper area). None of those docs cross-referenced `copper_balance`'s
`total_area_mm2`, so this is the first time the two numbers have been
compared directly -- and they match exactly.

**Independent third confirmation, via KiCad's own engine** (`pcbnew`,
bundled with the installed KiCad 10.0.4 at `/Applications/KiCad/KiCad.app`,
run via its own Python 3.9, not `temper_placer` code):

```
board.GetBoardEdgesBoundingBox() -> 152.100 x 234.100 mm = 35,606.61 mm²
```

The 0.11% difference (35,606.61 vs 35,568) is exactly explained by the
`Edge.Cuts` line's own 0.1mm width (KiCad's bbox includes the drawn line's
half-width overhang on each side; `copper_balance.py`'s `board.width *
board.height` uses the polygon vertices directly, i.e. the inside line).
Not a bug in either direction -- two different, both-legitimate
conventions for "the board's area," agreeing to four significant figures.

**Conclusion: `total_area_mm2 = 35,568` is correct.** It is `Board.width *
Board.height` (`packages/temper-placer/src/temper_placer/router_v6/
copper_balance.py:136`), where `Board.width`/`.height` derive from the
outline polygon's bounding box (`core/board.py:from_polygon`). The
"implausible" flag carried over from `docs/evidence/
2026-07-27-committed-route.md` and repeated in `2026-07-27-drc-checks-repaired.md`
was **itself an unverified guess that does not survive scrutiny** -- 152mm
x 234mm (roughly 6" x 9.2") is not an unreasonable footprint for an
induction-cooktop control board sitting under/beside a 180-220mm coil, and
matches the board's own placement-feasibility literature already in the
repo.

### A.2 Is the *area computation mechanism* buggy? Yes -- but not the way hypothesized

The task listed three candidate bug mechanisms to check: double-counted
overlapping polygons, mm/mil/nm unit confusion, and per-segment
bounding-box summation instead of real copper. None of those three is
present. Checked directly:

- **Unit confusion**: `Board.width`/`.height` are populated in mm
  throughout (`from_polygon` takes `(x, y)` mm vertices; no nm/mil
  conversion anywhere on this path). `copper_balance.py:136`'s
  `board_width * board_height` is a plain mm x mm multiply. Ruled out.
- **Segment-bbox summation**: `_calculate_layer_copper_area` (`copper_balance.py:166-230`)
  sums `trace_length * trace_width` per segment (a true swept-area
  rectangle sum, not a bounding-box sum) plus via annular-ring area
  (`π(r_pad² - r_hole²)`). Ruled out -- this part of the mechanism is
  geometrically sound *for the geometry it looks at* (see A.3).
- **Double-counted overlapping polygons in `total_area_mm2` itself**: the
  board-level constant (`total_area = board_width * board_height`,
  computed once, `copper_balance.py:127-136`) has no polygon-overlap logic
  at all -- it is a single rectangle multiply, computed once and reused as
  the denominator for every layer. Ruled out for `total_area_mm2`
  specifically.

**However, a real, confirmed "double counting the same copper" bug does
exist, just not on the path the task hypothesized (`total_area_mm2`) --
it is on the plane-net fallback path, and it is currently dead code, not
live.** `_calculate_layer_copper_area` (`copper_balance.py:184-193`)
special-cases any `compiled_route` with `width_mm == 0.0` as a "plane net"
and adds `total_area * 0.85` (the full board area) to that net's mapped
layer. `_PLANE_NET_LAYER` maps three GND-family nets (`GND`, `PGND`,
`CGND`) to the same layer (`In1.Cu`) and five power-family nets (`+15V`,
`+3V3`, `+5V`, `VCC`, `VDD`) to `In2.Cu` -- if more than one plane net in
the same family were simultaneously present in `routing_results.compiled_routes`
with `width_mm == 0.0`, that layer's reported area would be *N x 85% of
the board*, i.e. up to 255%+ coverage from double/triple-counting the same
physical pour. **This branch is provably unreachable on the current
pipeline**: traced every constructor of `CompiledRoute` in
`routing_results.py` (`compile_routing_results`, lines 145-222) -- the one
path that used to assign plane nets `width_mm=0.0` was changed (comment at
`routing_results.py:206-215`) specifically *because* a zero-width track is
a KiCad DRC `track_width` violation; plane nets are now always given a
positive `width_mm` (net's assigned width, or a 0.2mm floor) and an empty
`dummy_path` (`path_length=0.0`). Confirmed empirically: `width_mm == 0.0`
never appears in any of the 4 live re-route measurements taken for Part B
(all `compiled_route.width_mm` values were positive). This is a "Missing"
+ "Unwired" class bug per METHODOLOGY.md Sec 4 -- the double-counting
branch exists in the code and is exercised by none of this board's live
routing outcomes, so it is a **latent** bug, not a live one. Not fixed in
this task (fixing it well means either removing the dead branch or
reconciling it with the `width_mm=0.0`-can-never-happen invariant the 2026
route pipeline now enforces elsewhere -- a design decision, not a
one-line patch); flagged here so it cannot resurface silently if a future
change reintroduces `width_mm=0.0` plane nets.

### A.3 The real, live mechanism defect: blind to zone-pour copper

`copper_balance.py`'s own module docstring already discloses this:

> Copper pours, filled zones, and polygons are **not** currently
> accounted for in the copper area estimation. Only trace segments... via
> annular rings... and plane-net approximations are included.

`RoutingResults` (the only input `copper_balance.analyze_copper_balance`
receives) has **no field for zone/pour geometry at all** -- zones are
emitted directly to the exported `.kicad_pcb` by `zone_emission.py`,
outside the `RoutingResults` object entirely. This was previously an
acknowledged limitation with no board-scale evidence of impact. This task
supplies that evidence.

**Ground truth, via KiCad's own zone-fill engine** (`pcbnew.ZONE_FILLER`,
run directly against the committed `pcb/temper.kicad_pcb` -- the actual
zone-priority/clearance-resolved fill algorithm a real Gerber export
uses, not an approximation):

| Layer | Real filled zone copper | Real track copper | **True total** | **True %** | 30-70% balanced? |
|---|---:|---:|---:|---:|---|
| F.Cu | 3,199.84 mm² | 790.58 mm² | 3,990.43 mm² | **11.21%** | No |
| B.Cu | 2,982.37 mm² | 880.78 mm² | 3,863.15 mm² | **10.85%** | No |
| In1.Cu | 0.00 mm² | 0.00 mm² | 0.00 mm² | **0.00%** | No |
| In2.Cu | 0.00 mm² | 0.00 mm² | 0.00 mm² | **0.00%** | No |

(Board area used: KiCad's own 35,606.61 mm² bbox; using 35,568 changes
these percentages by <0.11%, not the verdict.)

Cross-check: the committed board's 96 `(zone ...)` blocks carry **zero**
`(filled_polygon ...)` sub-elements (`grep -c filled_polygon
pcb/temper.kicad_pcb` = 0) -- the committed file has never been run
through a zone-fill pass. The zone *outline* polygons (what `pcbnew`
resolves at fill time) overlap each other massively when read naively
(`DC_BUS_RTN` alone claims 52% of the board on `F.Cu`, `PWR_RTN` another
47.6%, summing past 100% together) -- an outline is "where this net's pour
is allowed to grow," not the post-priority-resolution filled shape, so a
naive polygon-area sum over raw `(polygon (pts...))` blocks is **not** a
valid copper-area oracle either (tried first; abandoned once the >100%
overlap made it obviously wrong -- kept as a documented dead end, not
presented as a measurement). Only `pcbnew`'s real fill engine gives a
trustworthy per-layer number.

**What this means for `copper_balance.py`'s live numbers:** on every one
of the 4 live `route_pcb(..., enable_manufacturing_drc=True)` runs taken
for this task (Part B; all 4 landed on bit-identical outcomes -- see Part
B.1), `copper_balance`'s own per-layer report showed F.Cu / In2.Cu / B.Cu
at a **literal 0.0 mm² / 0.0%** -- not "low," *zero* -- because that
particular in-memory re-route happened to place 100% of its discrete
trace segments on `In1.Cu` and the check cannot see the zone pours the
*same design intent* would place on the other three layers (confirmed
present and substantial on the committed file: F.Cu 11.2%, B.Cu 10.85%,
per the `pcbnew` oracle above). This is the reference-failure pattern
from METHODOLOGY.md Sec 7 in miniature: **a metric structurally blind to
the majority of what it claims to measure**, on a board where that blind
spot is not a corner case but the dominant copper source by design (plane
layers are supposed to be zone pours, not discrete traces).

### A.4 Do the 4 violations survive?

**Yes, but not for a trustworthy reason.** `copper_balance` flags all 4
layers in `STANDARD_LAYER_ORDER` (`F.Cu`, `In1.Cu`, `In2.Cu`, `B.Cu`) as
unbalanced (`is_balanced = 30% <= pct <= 70%`, all four fail on both the
live re-route numbers *and* the ground-truth committed-board numbers):

| Layer | Live re-route (copper_balance's own number) | Ground truth (committed board, pcbnew) | Both say unbalanced? |
|---|---:|---:|---|
| F.Cu | 0.0% | 11.21% | Yes (both <30%) |
| In1.Cu | 2.81% | 0.00%* | Yes (both <30%) |
| In2.Cu | 0.0% | 0.00% | Yes (both <30%) |
| B.Cu | 0.0% | 0.00% | Yes (both <30%) |

\* The live re-route and the committed board are two **different** route
outcomes -- the committed board was written by an earlier, separate
routing session (`docs/evidence/2026-07-27-committed-route.md`, 51/96
completion, 48 vias) that this task's live re-routes (38.5% completion, 0
vias, see Part B.1) did not reproduce byte-for-byte. The live re-route
happened to route everything onto `In1.Cu` (2.81%) while the committed
board's zone/track copper landed at 0% on `In1.Cu` and non-zero on
F.Cu/B.Cu. Neither is "the" answer for the other's file -- they are shown
side by side to make the point that **the check's own trace-only number
and the true zone-inclusive number for the same layer can differ by an
arbitrary, unbounded amount** (0% vs 11.2%) depending entirely on which
layer a given route outcome happened to drop discrete segments on,
independent of the real, physical plane copper that would exist on a
manufactured board.

**Verdict: the 4-unbalanced-layer count survives as a boolean (all 4
layers really are under the 30% floor on the actual committed board, per
the independent `pcbnew` oracle), but `copper_balance.py`'s own per-layer
area/percentage numbers are not measuring the right thing and cannot be
trusted in general** -- only the current board's numbers happen to be far
enough from the 30-70% band in both the buggy and the corrected
measurement that the verdict doesn't flip. A board with real,
well-designed ground/power planes reaching 35-50% true coverage would
still be reported as "0% / unbalanced" by this check today, because it
structurally cannot see zone-pour copper. **Denominator for both
measurements: 4 layers checked, 4 layers unbalanced, before and after.**
Fixing the mechanism (plumbing zone-fill area into `RoutingResults` or a
sibling data path) is a real, ranked follow-up, not attempted in this
task -- it requires threading zone geometry through the router pipeline
end-to-end, a larger change than a numeric correction, and the current
board's verdict does not depend on it.

---

## PART B -- the 16 clearance violations across 666 conductor pairs

### B.1 Reproduction, invocation, and a newly-found "Missing" class bug

**Exact invocation** (same technique as `docs/evidence/
2026-07-27-committed-route.md` / `2026-07-27-drc-checks-repaired.md`: a
monkeypatch on `RouterV6Pipeline.run` to capture the full
`RouterV6Result`, since `route_pcb()`'s own return type strips
`manufacturing_report`):

```python
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.netclass_loader import load_netclass_rules
from temper_placer.router_v6.adapter import route_pcb
netlist = parse_kicad_pcb(PCB).netlist
stub = make_parsed_pcb_stub(PCB, netlist)   # tests/conftest.py helper
rules = load_netclass_rules(RULES)
res = route_pcb(stub, {}, design_rules=rules.design_rules,
                 enable_zone_pours=True, enable_manufacturing_drc=True)
```

Full harness: `/private/tmp/claude-501/.../scratchpad/repro_clearance_copper.py`
(not committed; scratch tooling per task instructions).

Before touching any check code, this reproduced the task's stated
baseline **exactly** on the first independent run: completion 38.5%
(37/96 nets, `RoutePath3D` for all 37, i.e. matches "38.5% complete with
ZERO vias placed"), 0 vias in `compiled_routes`, `clearance.total_checks
== 666`, `clearance.violation_count == 16`.

**Run-to-run spread, N=4, before any fix** (each a separate process
invocation, same code/input):

| Run | Wall (s) | Completion | nets compiled | tree-routed | violation_count | total_checks |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 336.8 | 38.5% (37/96) | 37 | 0 | 16 | 666 |
| 2 | 332.3 | 38.5% (37/96) | 37 | 0 | 16 | 666 |
| 3 | ~332 (batched w/ run 4, see UNVERIFIED) | 38.5% (37/96) | 37 | 0 | 16 | 666 |
| 4 | ~332 (batched w/ run 3, see UNVERIFIED) | 38.5% (37/96) | 37 | 0 | 16 | 666 |

**Unexpected finding: this specific invocation is fully deterministic,
contradicting the router's documented 37.5%-53.1% completion spread.**
Not just the counts -- the exact set of 16 `(layer, location)` pairs is
**bit-identical across all 4 runs** (same 16 `(x, y)` coordinates, same
layer, to the full float precision captured). `docs/evidence/
2026-07-27-committed-route.md` measured 37.5%-53.1% completion spread on
"identical code and input"; this task's 4 samples show zero spread. The
difference is plausibly the call shape: this task's harness (matching
`docs/evidence/2026-07-25-outline-ab-experiment.py`'s pattern, also used
by the two prior sibling evidence docs for their own live measurements)
passes `placements={}` (empty dict, "route with existing board
positions") and a fixed `sat_conflict_limit=20_000` (the `route_pcb`
default) -- if the prior 37.5%-53.1% measurements used a different
`placements` dict, a different SAT bound, or ran under different
thread/hash-seed conditions, that would explain the discrepancy without
either measurement being wrong. **Root cause of the discrepancy is
UNVERIFIED** -- not diagnosed further, since router-internals
non-determinism is explicitly out of scope for this task, and 4/4
identical outcomes is itself sufficient grounds (per the task's own N>=4
instruction) to treat the 16/666 numbers below as a real, reproducible
measurement for this specific invocation rather than a single lucky
sample.

**A previously-undiscovered "Missing" class bug, found and fixed in this
task:** `verify_clearance` (`clearance_check.py`, both the Python
reference implementation and the Rust-backed default) walked only
`routing_results.compiled_routes` -- exactly the same blind spot
`annular_ring` had for its vias before `docs/evidence/
2026-07-27-drc-checks-repaired.md` fixed it. `RoutingResults.tree_routes`
/ `.partial_tree_routes` hold `CompiledTreeRoute` objects (Steiner
multi-terminal routes) with their own copper geometry and vias; any net
routed as a tree was **completely invisible** to clearance checking --
neither checked against other tree-routed nets, nor against
`compiled_routes` nets. Fixed: `_extract_segments`/`_extract_via_points`
now duck-type on `CompiledTreeRoute.geometry` (via
`TreeRouteGeometry.iter_segments()`, which keeps per-branch segments
separate so no phantom connecting segment gets fabricated between
branches), and a new `_all_routes()` helper feeds
`compiled_routes + tree_routes + partial_tree_routes` into both the
Python and Rust code paths (`packages/temper-placer/src/temper_placer/
router_v6/clearance_check.py`).

Regression tests (`test_clearance_check.py::
test_verify_clearance_inspects_tree_routed_nets` and
`::test_verify_clearance_checks_compiled_against_tree_routed`, both
parametrized over `backend=["python","rust"]`): confirmed failing before
the fix (`total_checks == 0`, both new tests, both backends -- checked via
`git stash` on `clearance_check.py` alone) and passing after (`total_checks
== 1`, `violation_count == 1` for an intentionally-overlapping pair in
each test).

**Is this dormant or live on the temper board?** Dormant, currently: **0
of 4** sampled live re-routes produced any tree-routed nets
(`n_tree_routes == 0`, `n_partial_tree_routes == 0` in every run) -- all
37 successfully-routed nets landed in `compiled_routes` every time. So
this fix does not move the 16/666 number on this specific board's
observed outcomes, exactly like `annular_ring`'s tree-route fix was
"proven at the unit level only" per the prior evidence doc. It is a real,
durable correctness fix (prevents recurrence on any future board/route
outcome that does use tree routing -- Steiner routing is a real code path
this router uses, just not exercised by any of this task's 4 samples),
kept because the user's own standing guidance is explicit: a
newly-discovered error *class* gets a systemic fix, not a one-board
patch.

**A second, more severe "Wrong" class bug, found and fixed in this
task -- the HV-net classification gate:** `_get_required_clearance`
determines whether a net pair gets the real IEC 60335 mains/DC-bus
clearance requirement (multiple mm) or the plain default (0.127mm) by
matching 4 hardcoded substrings (`"AC_"`, `"HV_"`, `"HIGH_VOLTAGE"`,
`"MAINS"`) against the net's own name. Checked directly against this
board's actual HV-domain net names (`elec/domain_manifest.yaml`'s `HV`
list):

```
DC_BUS_RTN vs gnd  -> required_clearance = 0.127 mm   (BEFORE fix)
+170V_BUS  vs gnd  -> required_clearance = 0.127 mm   (BEFORE fix)
PWR_RTN    vs +3V3 -> required_clearance = 0.127 mm   (BEFORE fix)
GATE_HS    vs gnd  -> required_clearance = 0.127 mm   (BEFORE fix)
ac_l       vs gnd  -> required_clearance = 14.0  mm   (already correct)
```

**Only `ac_l`/`ac_n` (2 of the manifest's 15 declared HV nets) were ever
recognized as HV** by the old substring gate, via the `"AC_"` substring
surviving `.upper()`. Every other real HV net on this mains-connected
board -- `DC_BUS_RTN`, `+170V_BUS` (the rectified/doubled DC bus,
~170V-referenced), `PWR_RTN`, `SW_NODE`, `GATE_HS`, `GATE_LS`, `+15V_LS`,
`w1_1`, `w1_2`, `zcd`, `a` -- was silently checked against every SELV net
(`gnd`, `+3V3`, RTD/MCU signals, ...) using the generic 0.127mm
default -- a ~99% shortfall from the task's own stated 3.0-8.0mm
requirement range, on precisely the pairs (mains/DC-bus vs. SELV control)
that requirement exists for. This is the single most safety-relevant
mechanism defect found in this task.

**Fix:** `_load_manifest_hv_net_names()` (new, `clearance_check.py`)
reads `elec/domain_manifest.yaml`'s `HV` domain -- the project's own
canonical, human-reviewed HV/SELV declaration, the same file
`scripts/check_domain_partition.py` already uses to answer the identical
question at the netlist level -- and ORs it into the existing substring
gate in both `_get_required_clearance` and `_classify_net_class`. This
was chosen over inventing a second hand-maintained keyword list (which
is exactly how the original gap happened) specifically so the check's HV
boundary cannot silently drift from the project's single declared source
of truth. Degrades to the substring heuristic alone (never raises) if the
manifest cannot be found or parsed -- this is a reporting-only DRC check,
not a hard gate, and must not crash the router pipeline over a file it
never previously depended on.

Regression tests (`test_clearance_check.py::
test_required_clearance_recognizes_manifest_hv_nets_not_matched_by_keywords`,
`::test_required_clearance_default_for_non_manifest_selv_pair`): confirmed
failing before the fix (`ImportError` -- the loader function did not
exist -- and, functionally, `required_clearance == 0.127` for
`DC_BUS_RTN` vs `gnd`) and passing after (`required_clearance == 14.0`
for the same pair; the SELV-SELV sanity check still returns the plain
0.127mm default, confirming the fix does not over-broaden HV
classification).

**Effect on the live 16/666 measurement:** re-measured N=4 with both
fixes applied -- see B.2 for the corrected counts and denominators. This
fix targets the *required-clearance threshold* used for each pair, not
the pair-count or a report cardinality, so per the hard rule against
shrinking denominators: this can only ever **increase** the violation
count relative to the pre-fix baseline (a pair that was previously
compared against 0.127mm and passed can now fail against a much larger
IEC 60335 requirement; no pair's requirement was ever lowered).

**A previously-undiscovered "Missing" class bug, found and fixed in this
task:** `verify_clearance` (`clearance_check.py`, both the Python
reference implementation and the Rust-backed default) walked only
`routing_results.compiled_routes` -- exactly the same blind spot
`annular_ring` had for its vias before `docs/evidence/
2026-07-27-drc-checks-repaired.md` fixed it. `RoutingResults.tree_routes`
/ `.partial_tree_routes` hold `CompiledTreeRoute` objects (Steiner
multi-terminal routes) with their own copper geometry and vias; any net
routed as a tree was **completely invisible** to clearance checking --
neither checked against other tree-routed nets, nor against
`compiled_routes` nets. Fixed: `_extract_segments`/`_extract_via_points`
now duck-type on `CompiledTreeRoute.geometry` (via
`TreeRouteGeometry.iter_segments()`, which keeps per-branch segments
separate so no phantom connecting segment gets fabricated between
branches), and a new `_all_routes()` helper feeds
`compiled_routes + tree_routes + partial_tree_routes` into both the
Python and Rust code paths (`packages/temper-placer/src/temper_placer/
router_v6/clearance_check.py`).

Regression tests (`test_clearance_check.py::
test_verify_clearance_inspects_tree_routed_nets` and
`::test_verify_clearance_checks_compiled_against_tree_routed`, both
parametrized over `backend=["python","rust"]`): confirmed failing before
the fix (`total_checks == 0`, both new tests, both backends -- checked via
`git stash` on `clearance_check.py` alone) and passing after (`total_checks
== 1`, `violation_count == 1` for an intentionally-overlapping pair in
each test).

**Is this dormant or live on the temper board?** Dormant, currently: **0
of 4** sampled live re-routes produced any tree-routed nets
(`n_tree_routes == 0`, `n_partial_tree_routes == 0` in every run) -- all
37 successfully-routed nets landed in `compiled_routes` every time. So
this fix does not move the 16/666 number on this specific board's
observed non-deterministic outcomes, exactly like `annular_ring`'s
tree-route fix was "proven at the unit level only" per the prior evidence
doc. It is a real, durable correctness fix (prevents recurrence on any
future board/route outcome that does use tree routing -- Steiner routing
is a real code path this router uses, just not exercised by any of this
task's 4 samples), kept because METHODOLOGY.md's user-memory guidance is
explicit: a newly-discovered error *class* gets a systemic fix, not a
one-board patch.

### B.2 Classifying the 16 by origin

*(This section is completed after the pad-position cross-reference and
the N=4 identity-stability check -- see the run-3/4 update below for the
final classification and denominators.)*
