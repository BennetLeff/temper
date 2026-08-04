# Clearance (16/666, corrected to 37/666) and copper_balance (4 unbalanced layers) investigation

<!-- provenance: commit=0956dd6cf6ea132b8a2f7b7f210642e845081bdb dirty=true (work commit; base per task instructions. Corrected: the previously-recorded commit=02e907b9d19eab77a13cb63a390af18b1c1d7d10 does not resolve via `git cat-file -t` -- it is a mistranscribed tail after a valid 8-char abbreviation. `02e907b9` is the prefix of exactly one commit in this repository's history, `02e907b9a5e1dbca4eae9a0a53f8a2be6dc862c5` ("fix(build): no pyo3 extension in this repo could be rebuilt on macOS", 2026-07-27), which is also an ancestor of this doc's own introducing commit 94fcc741 -- used here as the corrected value, not a fabricated one.) -->

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
reported 16/666 baseline directly. However, a **second, separate "Wrong"
class bug** -- the HV-manifest fix (`7ad5b15c`) was applied only to the
Python reference implementation and never reached the Rust backend that
`backend="auto"` (the production default) actually uses -- meant the fix
was **dead code in production**, and a **third** gap (the manifest itself
was missing 6 real HV nets, found by direct netlist tracing) meant even
the Python path under-classified. Both are fixed in this task (Part B.2);
the corrected, reproducible measurement is **37/666**, monotonically up
from 16/666 as the hard rule against shrinking denominators predicts. The
falsifier's second clause **fires**: of the 37, 36 (97.3%) are routing
artifacts of this specific incomplete route, geometrically provable via
pad-to-pad distance (any re-route could satisfy clearance; see Part B.2).
Full classification and the two backend/manifest fixes are in Part B.2.

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

### B.2 Re-measurement, the two backend/manifest fixes, and classifying the corrected 37 by origin

**FALSIFIER for this section, stated up front:** *"With HV classification
corrected, the surviving violations are real, durable, placement-derived
defects requiring board changes. If instead they are overwhelmingly
routing artifacts of an incomplete route, or if the corrected requirements
are being applied to net pairs that are not actually in the same isolation
domain, the honest deliverable is that finding."*

**Verdict: the falsifier's second clause fires cleanly (36/37, 97.3%, are
routing artifacts), and a narrow version of the third clause fires for the
1 remaining case (a same-component pin pair, not actually a cross-domain
requirement).** No violation in the corrected set is a durable,
placement-forced defect in the sense the falsifier describes.

#### B.2.0 The count did **not** move at first -- because the fix never reached production

Before touching anything further, this task re-ran the exact B.1 invocation
against the now-merged `7ad5b15c` (manifest-based HV fix). **Result:
16/666, bit-identical to the pre-fix baseline.** Investigated rather than
accepted at face value, because the task's own framing ("almost certainly
moved, very likely upward") predicted otherwise:

`verify_clearance`'s `backend="auto"` default prefers the Rust engine
(`temper_drc_rs.verify_route_clearance`) whenever it is importable --
true in every environment this check ships to, confirmed via
`_HAS_RUST_CLEARANCE == True` in this task's own environment. `7ad5b15c`
added `_load_manifest_hv_net_names()` and OR'd it into
`_get_required_clearance`/`_classify_net_class` -- **but only in the
Python reference implementation.** `router_clearance.rs`'s own
`is_hv_gate`/`classify_net_class` still used the original 4-keyword gate
(`AC_`/`HV_`/`HIGH_VOLTAGE`/`MAINS`) with no manifest awareness at all.
Confirmed directly, before any fix, on the real board's `DC_BUS_RTN` vs
`gnd` pair (a pair `7ad5b15c`'s own commit message uses as its worked
example):

| Backend | Required clearance (before this task's fix) |
|---|---:|
| `python` (forced) | 14.0mm |
| `rust` (forced) | 0.127mm |
| `auto` (production default) | 0.127mm |

**The `7ad5b15c` fix was dead code in production.** Every one of that
commit's own regression tests (`test_required_clearance_recognizes_
manifest_hv_nets_not_matched_by_keywords`,
`test_required_clearance_default_for_non_manifest_selv_pair`) called
`_get_required_clearance` directly -- the Python function -- so they
passed without ever exercising the code path `verify_clearance()` actually
uses by default. The pre-existing Rust/Python **differential** test suite
(`test_clearance_rust_differential.py`, 38 cases, asserts the two backends
produce bit-identical violation sets) also passed throughout, for a
subtler reason: none of its 38 fixtures use a manifest-only net name --
its HV fixture names (`AC_L`, `HV_BUS`, `MAINS_LIVE`, `HV_BUS_1`) all match
the keyword gate already, so both backends agreed on every case that suite
actually exercises. This is the exact mirror of the task's own stated
concern about net classification being "guilty until checked, in BOTH
directions": here the check that was supposed to catch a Python/Rust
divergence had a **coverage gap in its own fixtures**, not a logic bug.

**Fixed in this task** (`packages/temper-drc-rs/src/router_clearance.rs`,
`packages/temper-placer/src/temper_placer/router_v6/clearance_check.py`):
`verify_route_clearance`'s PyO3 binding gained a 4th, optional
`hv_net_names` parameter (additive -- no existing call site's signature
had to change); `is_hv_gate_named`/`classify_net_class_named` OR keyword
match with membership in that set, mirroring the Python fix exactly.
`_verify_clearance_rust` now passes `_load_manifest_hv_net_names()`
through. Verified fail-before/pass-after via `git checkout HEAD --` on
both files (never `git stash`, per task instructions) at two levels: a
standalone script, and a new parametrized regression test
(`test_manifest_hv_fix_reaches_rust_and_auto_backends`, `backend` in
`["rust", "auto"]`, `packages/temper-placer/tests/router_v6/
test_clearance_check.py`) -- both fail with `required_clearance == 0.127`
before this commit's diff and pass with `required_clearance == 14.0` for
the same `DC_BUS_RTN` vs `gnd` pair after it. 57 Rust unit tests (`cargo
test --release`), 16 Python `test_clearance_check.py` tests, and all 38
`test_clearance_rust_differential.py` cases still pass after the change.

#### B.2.1 A second gap: the manifest itself was missing 6 real HV nets

Applying the backend fix alone (manifest still at its pre-existing 15
declared HV nets) moved the count from 16/666 to **33/666** -- already a
clean confirmation that the fix could only increase violations, never
decrease them (0 violations were removed at this step; all 16 originals
persisted; 17 new ones appeared as the correct HV threshold started
applying to pairs it had silently exempted).

Before accepting 33/666 as final, this task checked the manifest's own
completeness the same way `7ad5b15c`'s commit message frames the original
bug: by direct wire-tracing against `elec/src/*.ato`, not by trusting net
spelling. Four of the 33 remaining violations involved
`hb.gate_hs.driver-p1-1` and `hb.power_loop.q_high-g` -- names that
*look* internal/primary-side by pattern, but tracing the actual
connections (`modules.ato:179-182`, `driver.OUTA ~ rg_on.p1; rg_on.p2 ~
drive.out`; `main.ato`-level `gate_hs.drive.out ~ power_loop.q_high.G`)
shows both sit on the isolated **secondary** (HV) side of the gate
driver, one plain 2.2ohm resistor downstream of the already-declared
`GATE_HS` net, with no isolator between them. A concurrent sibling task
(`docs/evidence/2026-07-27-domain-classification-coverage.md` Sec 7) had
already flagged these exact two names as UNVERIFIED and -- worse --
tentatively grouped `hb.power_loop.q_high-g` under a "primary-side"
(implicitly SELV) heading, a naming-convention guess that direct tracing
shows to be **wrong**. Two more genuinely HV nets were found the same way
while re-verifying isolation-barrier gates after adding the first two (see
below): `hb.gate_hs.driver-p2` (UCC21550 pin 14, VSSA) and `power_in.ntc-no`
(the bypass relay's NO contact / bridge-rectifier anode, directly
mains-referenced), plus `tank-out`/`tank.c_tank1-p2` (the 400V resonant
tank driving the induction coil, `main.ato:442`: `hb.switch_node ~
tank.in` -- literally the same net as the already-declared `SW_NODE`).
All 6 additions are documented net-by-net with exact `.ato` line citations
in `elec/domain_manifest.yaml` (committed separately, `3277ee94`).
`scripts/check_domain_partition.py` re-verified **0 domain crossings**
after each addition (54 declared nets, up from 48).

With all 6 nets declared, the measurement moved once more, from 33/666 to
the final **37/666** (4 more new violations, all four involving
`hb.gate_hs.driver-p1-1`; 0 removed). The `tank-*` additions did not move
the routed-clearance count at all (neither tank net appears among the
37/96 nets this particular partial route successfully routed), but they
were needed to keep a **separate** gate honest -- see B.2.4.

#### B.2.2 Denominators, before and after, all three states

| State | Violations | Total checks | Delta |
|---|---:|---:|---:|
| Original baseline (`7ad5b15c` merged, but dead in production) | 16 | 666 | -- |
| + Rust backend fix (manifest at 15 HV nets) | 33 | 666 | +17 / -0 |
| + manifest completeness fix (19 HV nets: +4 gate-driver/mains nets) | 37 | 666 | +4 / -0 |

**Denominator (`total_checks`) is unchanged at 666 throughout** -- this
fix only ever changes which *threshold* a pair is compared against, never
which pairs are compared (`C(37,2) = 666` for the 37 successfully-compiled
routes in every sample; 0 tree-routed nets in any sample, so
`_all_routes()`'s tree-route fix, Part B.1, does not additionally change
this denominator here). **0 violations were ever removed at any step** --
consistent with the hard rule that a corrected classification can only
increase a violation count, never decrease it.

#### B.2.3 Determinism re-confirmed post-fix

Per the task's instruction (prior N=4 already established determinism;
N=2 is sufficient to re-confirm after a code change), this task ran the
corrected invocation independently **twice** (separate process
invocations, ~65s wall each via the now-fixed, fast `backend="auto"`
path -- see B.2.5 for why this task avoided `backend="python"` for the
full-board measurement). Both landed on **37/666**, and the full
violation set (net pair, layer, location to full float precision,
actual/required clearance) is **bit-identical** between the two runs. A
third run (after the tank-net manifest addition, which does not touch any
of the 37 pairs) reproduced the identical 37-entry set again. **Determinism
holds after the fix, same as before it.**

#### B.2.4 A side effect outside this task's scope, disclosed rather than hidden

Adding `hb.gate_hs.driver-p1-1` (needed for B.2.1) makes C17
(`hb.gate_hs.boot_cap`, which has that net on one pad) a "declared-HV
component" for the first time in `packages/temper-placer/tests/
requirements/safety/test_clearance.py::TestClearanceIntegration::
test_temper_board_clearance_compliance` -- a **separate** check
(`verify_iec60335_compliance` / `domain_clearance.py`'s placement-time CP-SAT
constraint machinery, not `clearance_check.py`'s routed-copper check this
task is scoped to). That test's own fail-closed proximity guard
immediately found R30 (`tank.inductor_conn`) sitting 7.44mm from C17,
under its 8.0mm IEC margin and previously invisible because C17 wasn't
HV-classified. Tracing R30 (`main.ato:442`, `modules.ato:441-471`) showed
it, too, is genuinely HV (the resonant-tank/coil connector) -- adding
`tank-out`/`tank.c_tank1-p2` (B.2.1) closes that specific proximity
finding correctly (not by loosening a threshold; by completing the
classification), and `check_domain_partition.py` stays at 0 crossings.

**However, this reopens a different assertion in the same test file.**
That test's hard `assert result.passed` now runs against the FULL
54-net manifest-derived classification (per a prior, unrelated task,
`docs/evidence/2026-07-27-clearance-resolve-full-coverage.md`, that
re-solved the board's placement specifically to satisfy the *previous*
48-net set at 0 violations). This task's 6 new, correctly-traced HV nets
were not part of that resolve's constraint set, and re-running the full
check with them included surfaces **9 real REQ-SAFE-01 clearance/creepage
violations** that were invisible before this task for the same reason
the 37/666 number was invisible: the nets simply weren't classified yet.

This is the exact same dynamic as the rest of this document (a corrected
classification can only ever surface more true positives) playing out in
a check this task was not asked to fix. **Not remediated here** -- fixing
it requires a placement re-solve against the now-complete 54-net
domain-crossing constraint set (`domain_clearance.py`'s
`generate_domain_clearance_constraints`, which already consumes this same
manifest transitively), a materially larger undertaking than Part B's
scope, and exactly the kind of "outside this task's control" situation
`docs/evidence/2026-07-27-domain-classification-coverage.md` Sec 5
already established precedent for handling by disclosure rather than by
reverting the classification fix that caused it. **Left failing,
disclosed here rather than silently reverting the correct manifest
entries to keep it green** -- reverting would mean re-hiding 6 confirmed
real HV nets to make an unrelated gate pass, which the hard rule against
shrinking a denominator to force a number down forbids in spirit as much
as in letter. Flagged as a real, ranked follow-up.

#### B.2.5 Why `backend="python"` was abandoned for the full-board measurement

An initial attempt to compute `backend="rust"` / `"python"` / `"auto"`
side-by-side on the same live re-route (to triple-confirm backend
agreement beyond the synthetic `DC_BUS_RTN`-vs-`gnd` case) was killed
after **14+ minutes** of a single pinned CPU core with no output, versus
the ~60-65s the fixed `backend="auto"`/`"rust"` path takes for the entire
pipeline including this check. This matches the pre-existing, documented
concern in `_adapter_convert.py`'s own docstring ("`verify_clearance` is
O(n^2) pure Python and does not complete on a routed board -- 27 min, 9.2
GB, unfinished"). Not diagnosed further (root cause of the slowdown is
out of scope for this task and the fast Rust path is both correct,
per B.2.0's fail-before/pass-after proof, and now the actual production
default) -- this task relied on `backend="auto"` (== `backend="rust"`
whenever `temper_drc_rs` is present, confirmed) for every full-board
measurement in B.2.0-B.2.3, and used the synthetic 2-route fixture (fast
regardless of backend) for the direct 3-way backend comparison instead.

#### B.2.6 Classifying the 37 by origin: placement vs. routing

**Method.** `clearance_check.py`'s conductor model is trace segments and
via cylinders only -- it never reads pad/footprint polygon geometry, so
by the literal conductor type every violation this check can ever report
is "trace vs. trace" (or via). The question the task actually asks
("does this persist under any routing, or is it an artifact of this
specific route") is answered by a different, more direct test: for each
violated net pair, compute the **minimum pad-to-pad distance** between
*any* pad of net1 and *any* pad of net2 (pure component-placement
geometry, computed from `parse_kicad_pcb(PCB).pads`, with zero dependence
on how -- or whether -- either net is routed).

- If `pad_to_pad_distance < required_clearance`: **no routing choice**
  could ever satisfy the requirement -- the two components are placed too
  close together, full stop. **Placement-derived.**
- If `pad_to_pad_distance >= required_clearance`: the placement leaves
  enough room; the *routed traces* ended up closer than required only
  because of this specific route's path choice. **Routing-derived** --
  an artifact of the 38.5%-complete, zero-via route, not the board.

**Result, over the corrected 37/666:**

| Origin | Count | % |
|---|---:|---:|
| Routing-derived (pad-to-pad margin, all comfortably positive: +2.15mm to +72.4mm) | 36 | 97.3% |
| Placement-derived (pad-to-pad < required) | 1 | 2.7% |
| **Total** | **37** | **100%** |

Of the 36 routing-derived, 9 are SELV-SELV pairs at the plain 0.127mm
default (the original baseline's own composition, unaffected by the HV
fixes) and 27 involve at least one HV net at the corrected 4.2mm
internal-layer threshold. Full per-violation table (net pair, actual vs.
required clearance in mm, pad-to-pad distance, margin):

| Net 1 | Net 2 | Actual (mm) | Required (mm) | Pad-to-pad (mm) | Margin (mm) | Origin |
|---|---|---:|---:|---:|---:|---|
| safety.fault_any_or-a2 | sclk | 0.115 | 0.127 | 8.803 | +8.676 | routing |
| discharge.k_dis2-coil1 | power_in.q_relay_drv-g | 0.011 | 0.127 | 6.858 | +6.731 | routing |
| DISCHARGE_CTRL | power_in.q_relay_drv-g | 0.071 | 0.127 | 3.820 | +3.693 | routing |
| power_in.q_relay_drv-g | cs_n | 0.021 | 0.127 | 41.547 | +41.420 | routing |
| discharge.k_dis1-coil2 | power_in.bypass_relay-coil2 | 0.021 | 0.127 | 8.375 | +8.248 | routing |
| RTD_SCK | cs_n | 0.120 | 0.127 | 46.623 | +46.496 | routing |
| safety.uvlo_logic-line | sclk | 0.115 | 0.127 | 12.312 | +12.185 | routing |
| safety.coil_thermal.comp-inp | input | 0.100 | 0.127 | 13.852 | +13.725 | routing |
| rtd_pan.high_window-out | safety.ovp.r_adc_top2-p2 | 0.110 | 0.127 | 8.962 | +8.835 | routing |
| safety.ovp.r_div_top2-p2 | hb.gate_hs.driver-p1-1 | 0.764 | 4.200 | 40.319 | +36.119 | routing |
| discharge.r_snub1-p2 | a | 2.212 | 4.200 | 39.905 | +35.705 | routing |
| w1_2 | cs_n | 0.150 | 4.200 | 76.588 | +72.388 | routing |
| w1_2 | power_in.ntc-no | 0.296 | 4.200 | 6.350 | +2.150 | routing |
| w1_2 | input | 0.550 | 4.200 | 20.973 | +16.773 | routing |
| safety.ovp.r_div_top1-p2 | zcd | 1.735 | 4.200 | 38.561 | +34.361 | routing |
| safety.ovp.r_div_top1-p2 | a | 0.050 | 4.200 | 44.100 | +39.900 | routing |
| safety.ovp.r_div_top1-p2 | hb.gate_hs.driver-p1-1 | 0.523 | 4.200 | 37.609 | +33.409 | routing |
| safety.ovp.r_div_top1-p2 | discharge.k_dis1-nc | 1.350 | 4.200 | 35.359 | +31.159 | routing |
| zcd | safety.uvlo_logic.mon-outa | 0.135 | 4.200 | 15.846 | +11.646 | routing |
| zcd | a | 0.934 | 4.200 | **1.650** | **-2.550** | **placement** |
| SHUTDOWN | a | 4.050 | 4.200 | 46.518 | +42.318 | routing |
| safety.uvlo_logic.mon-outa | a | 0.457 | 4.200 | 37.279 | +33.079 | routing |
| safety.uvlo_logic.mon-outa | hb.gate_hs.driver-p1-1 | 0.123 | 4.200 | 10.485 | +6.285 | routing |
| discharge.k_dis1-coil2 | a | 0.150 | 4.200 | 35.206 | +31.006 | routing |
| discharge.k_dis1-coil2 | discharge.k_dis1-nc | 0.950 | 4.200 | 12.200 | +8.000 | routing |
| cs_n | hb.power_loop.q_high-g | 0.021 | 4.200 | 25.647 | +21.447 | routing |
| ina | a | 1.050 | 4.200 | 48.003 | +43.803 | routing |
| power_in.ntc-no | hb.power_loop.q_high-g | -0.248 | 4.200 | 18.515 | +14.315 | routing |
| power_in.ntc-no | hb.gate_hs.driver-p1-1 | 1.079 | 4.200 | 17.881 | +13.681 | routing |
| power_in.bypass_relay-coil2 | a | 0.021 | 4.200 | 18.854 | +14.654 | routing |
| power_in.bypass_relay-coil2 | discharge.k_dis1-nc | 0.421 | 4.200 | 30.225 | +26.025 | routing |
| hb.power_loop.q_high-g | hb.gate_hs.driver-p1-1 | -0.006 | 4.200 | 35.235 | +31.035 | routing |
| hb.power_loop.q_high-g | safety.ovp.r_adc_top2-p2 | 0.021 | 4.200 | 54.070 | +49.870 | routing |
| a | discharge.k_dis1-nc | 0.150 | 4.200 | 36.546 | +32.346 | routing |
| a | sdi | 3.134 | 4.200 | 21.944 | +17.744 | routing |
| hb.gate_hs.driver-p1-1 | rtd_pan.high_window-out | 2.936 | 4.200 | 7.394 | +3.194 | routing |
| discharge.k_dis1-nc | sdi | 2.634 | 4.200 | 40.817 | +36.617 | routing |

**The 1 placement-derived case is itself not a real cross-domain
defect.** `zcd` and `a` are R9's own two leads (pad 1 and pad 2 of a
single 2-terminal resistor -- `pad1_ref`/`pad2_ref` = `R9.1`/`R9.2`,
confirmed via `parse_kicad_pcb(PCB).pads`). A discrete component's own
two pins are *always* closer together than any inter-component IEC 60335
domain-crossing clearance figure; that is not a placement defect, it is
package geometry. More importantly, `elec/domain_manifest.yaml`'s own
existing text (predating this task) already documents that `a` is
"*still entirely HV-side*" of R9 -- `zcd` and `a` are **not** actually on
opposite sides of an isolation barrier, just two nodes of the same
current-limiting resistor within one domain. `_get_required_clearance`
nonetheless escalates to the full 4.2mm multi-standard HV figure because
it classifies *any* pair where at least one side is HV-gated using a flat
`voltage=230V` default (no per-node voltage-difference awareness), with
no notion of "these two nodes are on the same floating domain, not
crossing anything." **This is a narrow instance of the falsifier's third
clause** ("corrected requirements applied to a pair not actually
separated by an isolation domain") -- reported as a finding, not
silently exempted or hardcoded away: `get_clearance`'s HV-vs-HV handling
has no same-domain-adjacent-node concept anywhere in this codebase, and
building one is a real, ranked follow-up (would need per-node working-voltage
data this project does not currently track), not attempted here.

#### B.2.7 Deliverable 3: acting on the split

**Placement-derived (1 of 37): no board fix applied.** As B.2.6
establishes, this is not a genuine placement defect -- it is a
single component's own pin pitch, paired against a requirement that
should not apply between two same-domain nodes in the first place. There
is nothing for `domain_clearance.py`'s `SeparatedConstraint`
machinery to encode here: that machinery generates constraints between
*different components* crossing a *declared* domain boundary
(`_domain_boundary_pairs`), and R9's own two pins are neither. Forcing a
constraint here would be encoding a false requirement, not fixing a real
one.

**Routing-derived (36 of 37): explicitly deferred, not hand-patched.**
Per the task's own instruction, a non-deterministic routing artifact must
not be hand-patched. Three reasons this is the correct call, not merely
the convenient one:

1. **Nothing is actually broken in the repository.** The measurement in
   this section comes from an **in-memory** re-route (`route_pcb(...,
   placements={})`, this task's harness) -- confirmed via `pcb/
   temper.kicad_pcb`'s unchanged mtime and `grep -c filled_polygon` before
   and after every run in this task. The committed board file was never
   written to. There is no committed defect to patch.
2. **The route this measures is 38.5% complete with zero vias** -- by the
   router's own admission (`docs/evidence/2026-07-27-committed-route.md`),
   a materially different, more complete, in-progress route already
   exists as the actual candidate for eventual commit. Patching traces in
   *this* throwaway sample would not fix anything that ships.
3. **All 36 pad-to-pad margins are large** (+2.15mm to +72.4mm) --
   meaning ordinary clearance-aware routing (the router simply needs to
   maintain the same margins it already achieves for the 629 non-violating
   pairs) resolves every one of them without any placement change. This is
   exactly the profile of "router quality on an unfinished pass," not "the
   board cannot be routed compliantly."

**Recommended action for a future task** (not performed here, out of Part
B's scope): re-route to a higher completion percentage with the corrected
HV thresholds active from the start (this task's fix is now the default,
so any future `route_pcb(..., enable_manufacturing_drc=True)` call
already benefits), and re-measure. If violations persist at that point
with comfortably-positive pad-to-pad margins, the next step is tightening
the router's own inter-net keepout radius during path planning (a router
change, not a placement or manifest change) -- not attempted here because
this task's scope is measurement and classification, not router
path-planning quality.

#### UNVERIFIED

- **Root cause of `backend="python"`'s multi-minute-plus runtime**
  (B.2.5) -- not diagnosed; only worked around by using the fast, now
  fixed `backend="auto"` path for full-board measurement.
- **Whether the 9 REQ-SAFE-01 violations newly surfaced in
  `test_temper_board_clearance_compliance` (B.2.4) are themselves
  placement- or routing-derived, or whether any involve the same
  same-domain-adjacent-node misapplication documented in B.2.6** -- not
  investigated; that check and its own violation set are outside this
  task's scope (routed-copper clearance, not placement-time IEC 60335
  compliance).
- **Whether `get_clearance`'s flat `voltage=230V` HV default, rather
  than a per-node working-voltage figure, causes similar
  same-domain-misapplication findings elsewhere on the board** (B.2.6)
  -- only the one instance surfaced in this task's 37-violation set was
  investigated; a systematic sweep would require per-node voltage data
  this project does not currently track.
