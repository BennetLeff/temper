# EMC Requirement Validators Implemented — emi_filter.py / ground_plane.py

**Date:** 2026-07-26
**Scope:** `packages/temper-placer/tests/requirements/validators/emi_filter.py` (8
stubs), `packages/temper-placer/tests/requirements/validators/ground_plane.py`
(4 stubs). `clearance.py`, `isolation.py`, `schematic.py` untouched (other
agent / deferred, per instruction).

---

## 1. Falsifier, stated before implementing

**Falsifier:** *If `check_star_ground_point`, given the post-SELV-float
architecture's real domain/connection data (the `gnd` SELV domain vs.
`PWR_RTN`, the HV doubler-midpoint return, crossed only by C6/PS1/T1/U3),
reports a violation — i.e. treats the current, correct, floated-and-isolated
design as broken — OR if it reports the removed `power_return ~ gnd` star
join as compliant, then the implementation has encoded the removed defect as
the requirement rather than validating the fixed architecture. That would be
the worst possible outcome for the highest-stakes validator in this batch.*

A secondary, batch-wide falsifier: *if any of the 12 stub functions, once
implemented, fails to raise a violation on a fixture built specifically to
contain the defect it claims to detect, the validator inspects nothing
meaningful — the same failure mode as the 0%-coverage stubs it replaces.*

**Result: neither falsifier fired.**

- `check_star_ground_point(real post-float domains)` → `passed=True,
  error_count=0`. `check_star_ground_point(reconstructed old defect: bare
  `gnd`↔`PWR_RTN` tie, no isolation marker)` → `passed=False`. Both asserted
  in `packages/temper-placer/tests/requirements/emc/test_ground_plane.py::
  TestGroundPlaneIntegration::test_temper_board_ground_plane_compliance`.
- Every one of the 12 functions has at least one test (pre-existing or added
  in this pass) that fails on a fixture constructed to contain the violation
  it detects — see the per-validator table in §3.

**`check_star_ground_point` validates the post-SELV-float architecture, not
the removed star join** — confirmed explicitly, see §4.

---

## 2. What was reused vs. written fresh

**Reused:**
- `packages/temper-placer/tests/requirements/validators/_geometry.py`'s
  existing `_distance`, extended (not duplicated) with polyline/segment
  helpers (`_point_to_segment_distance`, `_point_to_polyline_distance`,
  `_segments_intersect`, `_polyline_min_distance`, `_polylines_intersect`,
  `_polyline_length`) — shared by both target files, matching the
  established pattern (`bypass_caps.py` similarly adds a small local
  `_polygon_area` alongside the shared `_distance`).
- `temper_placer.io.kicad_parser.parse_kicad_pcb` for real component
  positions (`Component.initial_position`) — no new PCB parser written.
- `elec/build/default.csv` for reference-designator identity (per the task
  brief: `default.net` aliases identity by footprint, `.csv` does not).
- `docs/hardware/SELV_ISOLATION_REDESIGN.md` §4/§6's already-verified
  netlist crossing survey as the *source data* for the real-board
  `check_star_ground_point` run (not re-derived from the netlist a second
  time — that survey states it was itself derived by parsing
  `elec/build/default.net` programmatically).

**Deliberately NOT reused** (considered and rejected, with reasons):
- `router_v6/clearance_check.py`'s `verify_clearance` / `_segment_to_segment_dist`
  — operates on `RoutingResults` (compiled routes with per-layer widths and
  vias), not the plain `list[tuple[float, float]]` polylines this validator
  suite's function signatures use. Wrapping raw point-lists into
  `RoutingResults` objects just to call it would be more machinery than the
  problem needs; the closest-approach algorithm itself is standard
  (Ericson's clamped-projection method) and reimplementing the ~15-line
  version for bare tuples is not the "divergent duplicate" the task warns
  against — it operates one abstraction level lower.
- `temper-drc-rs`'s `emc::ground_plane` (component-in-zone check) and
  `routing::stitching_via_density` (nearest-neighbor via-gap heuristic on
  `BoardState`/`CopperZone`) — different data model (Rust `BoardState`, not
  Python dict fixtures) and different algorithm shape (nearest-neighbor
  max-gap vs. this suite's boundary-projected consecutive-gap model, which
  is what the pre-existing `check_via_stitching` test fixtures assume:
  vias along a *line*, not scattered in a zone polygon). Not the same check.
- `router_v6/creepage_check.py` / `constraints_geometry.py`'s private
  `_segments_intersect` — different dataclass types (`LineSegment`), private
  to their own modules; a fresh ~15-line orientation-test in the shared
  `_geometry.py` (used by exactly the two files in scope) was more
  appropriate than importing another module's private helper across an
  unrelated abstraction boundary.

---

## 3. Per-validator status

All 12 are **implemented** (none left raising `NotImplementedError`) — the
data each one's documented contract requires is present in the abstract
`dict`/`tuple` fixtures the suite already uses. Narrower sub-requirements
that could *not* be checked from the given data are called out per-row
rather than silently ignored.

### `emi_filter.py`

| Function | Status | Falsifier test | Note |
|---|---|---|---|
| `check_filter_signal_flow` | Implemented | `test_reversed_flow_fails` (pre-existing) | Canonical left-to-right order shared with `check_filter_component_order`. |
| `check_filter_component_order` | Implemented | `test_incorrect_order_fails`, `test_x_cap_before_cm_choke` (fixed, see §5), `test_y_caps_after_cm_choke` | |
| `check_x_cap_placement` | Implemented | `test_x_cap_connected_to_pe_fails` | PE-proximity threshold reuses the module's own 6mm L/N-PE figure (self-consistent, not invented). |
| `check_y_cap_placement` | Implemented | `test_y_caps_exceed_leakage_limit_fails` | Leakage-limit re-derivation attempted and **does not** cleanly reproduce the function's own 4.4nF default (see §6) — flagged rather than silently reconciled. |
| `check_mov_placement` | Implemented; **requirement direction corrected 2026-07-26 after coordinator review** | `test_mov_before_fuse_fails` (renamed/flipped, was `test_mov_after_fuse_fails`) | See §10 Addendum — the original "before or parallel to fuse" requirement was backwards for a safety-certified mains appliance. |
| `check_cm_choke_placement` | Implemented | `test_cm_choke_before_x_caps_fails`, `test_cm_choke_after_y_caps_fails` (added) | |
| `check_pe_trace_requirements` | Implemented, with a stated data gap | `test_pe_trace_width_below_minimum_fails` (added), `test_pe_trace_zigzag_not_direct_fails` (added) | Width can only be checked when trace points carry width as a 3rd tuple element (forward-compatible extension); the documented 2-tuple contract carries no width channel at all, so width is **unverified from that input shape** rather than fabricated. "Star ground at PE connection point" (docstring's 3rd requirement) is not checkable from this function's inputs at all — no domain/topology data is passed in; `check_star_ground_point` is the function that actually owns that check. |
| `check_line_neutral_pe_spacing` | Implemented | `test_insufficient_spacing_fails` (pre-existing, PE-to-neutral), `test_line_too_close_to_pe_fails` (added, PE-to-line) | |

### `ground_plane.py`

| Function | Status | Falsifier test | Note |
|---|---|---|---|
| `check_slot_lengths` | Implemented | `test_long_slot_fails` | |
| `check_signal_ground_reference` | Implemented | `test_trace_over_slot_fails` | Uses real segment-intersection, not a distance threshold — a trace either crosses a slot or it doesn't. |
| `check_star_ground_point` | Implemented — **validates the post-float architecture, not the removed join** | `test_multiple_connections_fail` (pre-existing), `test_direct_tie_into_isolated_domain_fails` (added, the SELV-critical case) | See §4. |
| `check_via_stitching` | Implemented | `test_insufficient_stitching_fails`, `test_no_vias_fails` | Fixed a float-epsilon bug during implementation (exact-spacing vias were flagged as 1e-15mm over the limit) — see §5. |

**No function was left `raise NotImplementedError`.** All 12 stub call sites
now execute real logic; every falsifier fixture above genuinely exercises
the `not result.passed` / `error_count >= 1` path, not a vacuous "always
returns passed=True" body.

---

## 4. `check_star_ground_point`: validates the fix, not the defect

This was the highest-risk function in the batch. The design **had** a
single-point star join (`main.ato: power_return ~ gnd`) that shorted a
4.2kVAC isolation barrier (Mean Well IRM-10-15 AuxSupply), and it was
**removed as a defect** — see
`docs/hardware/SELV_ISOLATION_REDESIGN.md`. A naive "exactly one connection
between two ground domains is correct" star-ground checker would have
signed off on exactly that defect (one connection *looks* like a textbook
star join even when it's actually a shorted barrier).

**Design used to avoid this:** two categorically different failure modes
live inside "star ground," and the implementation distinguishes them
instead of collapsing them into one rule:

- Between two domains that are **not** isolation-barrier sides of each
  other (e.g. a plain PGND/CGND split within one electrical system), a
  single direct tie is the correct pattern; more than one creates a ground
  loop (`SG-001`, matches the pre-existing `test_multiple_connections_fail`).
- Into a domain flagged **isolated** (either `{"isolated": True}` in its own
  entry, or named like `ISOGND` — matching the pre-existing test fixtures'
  own convention), a bare/direct connection is a barrier violation
  regardless of count (`SG-003`) — a connection is only legitimate there if
  it's tagged as going through a real isolation device (`component_type` in
  `{capacitor, transformer, optocoupler, opto, relay}`, or an explicit
  `isolated_via` marker).

**Run against the real board's post-float architecture** (data sourced from
`SELV_ISOLATION_REDESIGN.md` §4/§6, itself derived by parsing
`elec/build/default.net` programmatically — not re-parsed a second time
here):

```
gnd (isolated=True, PE-bonded, per main.ato: gnd ~ pe)  <->  PWR_RTN (HV doubler-midpoint return)
  crossed by:
    C6  (y_cap_pe, Y1 capacitor)      -- component_type: capacitor
    PS1 (IRM-10-15 AuxSupply)          -- component_type: transformer
    T1  (CST2010-100L current sense)   -- component_type: transformer
    U3  (H11L1, new in this change)    -- component_type: optocoupler
```

Result: **`passed=True`, `error_count=0`.** Correct — none of these four
crossings is a bare galvanic tie; each is a real, documented isolation
device.

**Counterfactual (the removed defect, reconstructed):** a single, unmarked
`{"from": "gnd", "to": "PWR_RTN"}` connection (i.e. exactly what
`power_return ~ gnd` was) → **`passed=False`**, flagged `SG-003`. The
checker would have caught the original defect had it existed at
implementation time.

Both runs are asserted in
`test_ground_plane.py::TestGroundPlaneIntegration::test_temper_board_ground_plane_compliance`.

---

## 5. Pre-existing test bugs found and fixed

These test files were previously either always-failing (`test_emi_filter.py`,
whose `VALIDATORS_AVAILABLE` guard only checked `ImportError`, so it never
actually skipped — see §7) or correctly skipped
(`test_ground_plane.py`), meaning none of their assertions had ever
genuinely executed to completion. Implementing the validators surfaced three
latent bugs in the tests themselves, unrelated to validator logic:

1. **`test_x_cap_before_cm_choke`** (`test_emi_filter.py`) put an X-cap in
   the `C_X2` slot after the choke and labeled it "wrong" — but this same
   module's own canonical order (`MOV, FUSE, L_DM, C_X1, L_CM, C_Y1, C_Y2,
   C_X2`) places `C_X2` *after* the choke by design (the output stage of a
   two-stage Pi filter). The test's own stated intent ("X-caps must be
   before CM choke") is true of `C_X1`, not `C_X2`. Fixed to use `C_X1`.
2. **`test_complete_filter_validation`** requested a fixture parameter named
   `_correct_filter_layout` (leading underscore) that does not exist — the
   real fixture is `correct_filter_layout`. This raised a collection-time
   "fixture not found" error the instant the module stopped being skipped.
   Fixed the name; the test still intentionally `pytest.skip()`s (out of
   scope — REQ-EMC-03's checks are implemented and tested independently,
   not as one aggregated function).
3. **`check_via_stitching`'s floating-point epsilon**: not a test bug but an
   implementation bug caught by `test_adequate_stitching_passes` — vias
   placed at exact 5mm intervals along a boundary projected to
   `5.000000000000001` due to float division, which then compared as
   `> 5.0` and falsely failed an exact-spacing fixture. Fixed with a
   `1e-6` tolerance on the gap comparison.

---

## 6. Standards assumptions, cited or flagged UNVERIFIED

- **CISPR 14-1** is the project's cited EMC reference for conducted
  emissions (`docs/FUNCTIONAL_TEST_CRITERIA.md` §3.1: "Minimize noise on AC
  lines (CISPR 14-1 Class B)"), specifying dBµV limits over 150kHz-30MHz —
  it does **not** specify PCB layout dimensions (trace spacing, slot
  length, Y-cap trace distance). Those thresholds come from general
  EMC/safety layout practice, not from CISPR 14-1 directly:
  - `check_line_neutral_pe_spacing`'s 6mm default and `check_x_cap_placement`'s
    reuse of the same figure: pre-existing in the stub's own signature, not
    re-derived here; treated as given.
  - `check_slot_lengths`'s 30mm default: pre-existing in the stub's own
    docstring (λ/2 antenna reasoning at 150MHz harmonics, conservative
    factor already stated there).
  - `check_y_cap_placement`'s Y-cap-to-PE-connection distance (15mm) and
    `check_x_cap_placement`/`check_mov_placement`'s lead-length warnings
    (10-15mm): **UNVERIFIED** heuristic numbers added in this pass, not
    sourced from any cited standard — flagged in the code comments at each
    site rather than presented as authoritative.
  - `check_pe_trace_requirements`'s directness tolerance (15% over
    straight-line distance): **UNVERIFIED**, same treatment.
- **IEC 60335-1** Class-I touch-current limit (3.5mA) is the stated basis
  for `check_y_cap_placement`'s 4.4nF default (per the stub's own
  docstring). Attempting the derivation independently in this pass
  (`C = I / (V·2πf)` at 3.5mA/250V/50Hz) works out to ≈44.6nF — an order of
  magnitude off the stated 4.4nF. **UNVERIFIED** whether the gap is a
  different assumed leakage limit (e.g. 0.35mA), a different reference
  voltage, or something else neither confirmed nor fabricated here; the
  implementation enforces whatever `max_total_capacitance_nf` the caller
  supplies rather than silently "fixing" the default to match a
  back-of-envelope number.

---

## 7. Test counts — before and after

Measured via `pytest -q` (foreground, no pipeline), counts read from the
summary line, not exit codes.

**Before** (original stub files, restored with `git stash` to measure a true
baseline, then popped back):

```
tests/requirements/emc/test_emi_filter.py:    23 collected -- 20 failed, 2 skipped, 1 error   (exit 1)
tests/requirements/emc/test_ground_plane.py:  15 collected -- 15 skipped                       (exit 0)
combined:                                      38 collected -- 20 failed, 17 skipped, 1 error   (exit 1)
```

Note the asymmetry: `test_ground_plane.py`'s import guard actually calls
`check_slot_lengths({}, ...)` and catches `NotImplementedError` to set
`VALIDATORS_AVAILABLE = False`, so it *did* skip correctly before this
change. `test_emi_filter.py`'s guard only catches `ImportError` (the module
always imported fine — the `raise` is inside the function bodies, not at
import time), so `VALIDATORS_AVAILABLE` was always `True` and its 20 tests
were **failing**, not skipped, every run. Both are "zero executed coverage"
in the sense the task means (nothing past the `raise` line ever ran), but
they were not both invisible in CI the same way — the `test_emi_filter.py`
failures should have been visibly red. This wasn't investigated further
here (out of scope — the task's exclusion of `schematic.py` and the note
about zero *continuous* coverage suggests these files may be excluded from
whatever CI invocation is actually gating; not re-litigated in this pass).

**After** (implementation complete, including 8 new falsifier tests, 2
pre-existing test bugs fixed, 2 real-board integration tests implemented):

```
tests/requirements/emc/test_emi_filter.py:    27 collected -- 25 passed, 2 skipped             (exit 0)
tests/requirements/emc/test_ground_plane.py:  17 collected -- 17 passed                        (exit 0)
combined:                                      44 collected -- 42 passed, 2 skipped             (exit 0)
```

The 2 remaining skips are both intentional and unchanged in intent from
before: `test_x_cap_trace_length` (trace-geometry width/length checking
explicitly out of scope, pre-existing `pytest.skip`) and
`test_complete_filter_validation` (aggregation-of-all-checks helper,
explicitly out of scope, pre-existing `pytest.skip`, fixture-name bug
fixed per §5 item 2).

Broader regression check: `pytest tests/requirements/ -q` →
**26 failed, 208 passed, 28 skipped, 7 errors** (unchanged from before this
change in every file *except* the two touched here — all 26 failures/7
errors are in `safety/test_isolation.py` (explicitly another agent's scope)
and `dfm/test_placement_rules.py` / `dfm/test_test_points.py` (untouched,
pre-existing, unrelated fixture/import issues). Zero failures or errors in
`emc/test_emi_filter.py` or `emc/test_ground_plane.py` in this combined run.

---

## 8. Every violation found on the real board

`pcb/temper.kicad_pcb` + `elec/build/default.csv` (built via `make netlist`,
exit 0, in this worktree — `elec/build/` is gitignored). Two structural
facts about the currently-committed board file, discovered while trying to
run these checks, matter more than any individual finding below:

- **Zero routed copper.** `grep -c '(segment' pcb/temper.kicad_pcb` → `0`.
  `grep -c '(via' pcb/temper.kicad_pcb` → `0`. A routed-percentage /
  violation-count figure describing a much-more-complete board appeared
  elsewhere in project documentation; it described a routing pipeline run's
  in-memory result, not this committed artifact, and has since been
  corrected there (`docs/STRATEGY.md`, commit `391ed5d3`) — not repeated
  here. The committed board is placed and entirely unrouted. This
  means `check_x_cap_placement`'s PE-proximity leg, `check_pe_trace_requirements`,
  and `check_line_neutral_pe_spacing` have **no trace geometry to check**
  today. Feeding them empty lists would report a vacuous "0 violations"
  pass that misrepresents "not routed yet" as "compliant" — **not run**,
  reported honestly as not-yet-applicable instead.
- **Zero copper zones.** `grep -c '(zone' pcb/temper.kicad_pcb` → `0`. No
  ground-plane pour exists yet at this stage of layout, so
  `check_slot_lengths`, `check_via_stitching`, and
  `check_signal_ground_reference` have **no ground-plane geometry to
  check**. Same treatment: **not run**, not fabricated as a pass.
- **The four remaining EMI-filter parts are not laid out on a common axis.**
  F1 (34.95, 72.0), RV1 (65.51, 173.72), L1 (35.5, 119.0), C1 (17.5, 15.0)
  span both X and Y widely. `check_filter_signal_flow` /
  `check_filter_component_order` / `check_cm_choke_placement` assume a
  left-to-right (x-only) flow axis — every unit-test fixture for them is
  collinear. **These checks infer topology from geometry, and that
  inference is unsound in general** — x-coordinate order is only a proxy
  for signal-flow order when a layout happens to be collinear along the
  flow axis, and nothing enforces that on a real 2D board. The
  `check_cm_choke_placement` finding below is a concrete demonstration:
  it produces a violation directly contradicted by the actual schematic
  topology. Whoever extends this family of checks (or feeds them real
  board data again after more routing exists) needs to know this going
  in, not discover it the way this pass did. Findings below are reported
  with that caveat and cross-checked against schematic-level netlist
  adjacency (`elec/src/modules.ato`) wherever possible, rather than
  trusted on geometry alone.

### Findings (real board, `elec/build/default.csv` identity: F1=fuse,
RV1=MOV, L1=CM choke, C1=X-cap `c_x2`, C6=Y-cap `y_cap_pe`)

| Check | Result | Corroboration |
|---|---|---|
| `check_mov_placement` (RV1 vs F1) | **PASS** (corrected 2026-07-26, see §10 Addendum — was reported as `FAIL` in the original version of this document; that was a wrong requirement, not a real design defect) | **Real, well-corroborated.** `elec/src/modules.ato` wires `fuse.p2 ~ mov.p1` — the MOV is downstream of the fuse, which is the *correct* requirement (an MOV's dominant failure mode is a short; downstream placement means the fuse interrupts a shorted MOV). Geometry (RV1 x=65.5 > F1 x=35.0) and topology agree, and the check now correctly reports this as compliant. |
| `check_filter_component_order` (MOV, FUSE, C_X1←C1, L_CM←L1) | **FAIL — 2×`FLOW-001`**: fuse should precede c_x1 but is placed after it; mov should precede l_cm but is placed after it | Axis-caveated (see above) — the MOV/FUSE pair itself is not implicated in either reported violation (both are about `c_x1`/`l_cm`), so the MOV/fuse correction (§10) doesn't change this row's output. Not independently corroborated beyond that. |
| `check_filter_signal_flow` (same 4 parts) | **FAIL — same 2×`FLOW-001`**, plus 3×`FLOW-ALIGN` warnings (parts are 47-102mm off a common flow axis) | Same axis caveat; the alignment warnings just quantify how non-collinear this layout is. |
| `check_cm_choke_placement` (L1 vs C1, C6) | **FAIL — `CMC-002`**: "Y-cap C6 (x=31.5) is before the CM choke (x=35.5)" | **Likely a false positive from the axis heuristic**, contradicted by topology: `modules.ato` chains `ac_n ~ cmc.W2_1 ~ cmc.W2_2 ~ dc_bus.gnd_ref`, and `dc_bus.gnd_ref ~ y_cap_pe.p1` — C6 is electrically *downstream* of the choke (correct, per canonical order), even though its raw x-coordinate sits to the left of the choke's. Reported as a concrete demonstration of why x-only geometry checks are unreliable on this specific non-collinear layout, not suppressed. |
| `check_y_cap_placement` (C6, 2.2nF) | **PASS** on the capacitance leg (2.2nF vs. the function's 4.4nF default — real margin, half the budget used by the one Y-cap in this design). PE-connection-distance leg **UNVERIFIED**: no discrete PE-stud/earth-terminal component exists in the BOM to supply a real `pe_connection` position distinct from C6 itself; proxying it to C6's own position makes that leg trivially (and uninformatively) pass rather than fabricating an arbitrary distinct point. | — |
| `check_x_cap_placement`, `check_pe_trace_requirements`, `check_line_neutral_pe_spacing` | **Not run** — no routed L/N/PE trace geometry exists in the committed board file (see above). | — |
| `check_slot_lengths`, `check_via_stitching`, `check_signal_ground_reference` | **Not run** — no copper zones/ground-plane pour exists in the committed board file (see above). | — |
| `check_star_ground_point` | **PASS** — see §4. The one function whose real-board data (net topology, not PCB copper geometry) is actually available today, and the one that matters most for the SELV redesign this task is grounded in. | Sourced from `SELV_ISOLATION_REDESIGN.md` §4/§6. |

**Also note:** no discrete AC input connector component exists anywhere in
this design (`ac_l`/`ac_n` are bare `PowerInput`-module-boundary signals;
`elec/build/default.csv`'s only `Connector`-class part is `J1`, a 2-pin
header unrelated to the mains input — confirmed by grep). Every check that
takes an `input_connector_position` argument used the fuse's own position
as an explicit, documented proxy (F1 is the first component `ac_l` reaches
with nothing electrically between them), not a fabricated connector
location.

---

## 9. Remaining UNVERIFIED items

- The four numeric heuristic thresholds listed in §6 (Y-cap PE-trace
  distance, X-cap/MOV lead length, PE-trace directness tolerance) —
  reasonable layout-practice guesses, not sourced from a cited standard.
- The IEC 60335-1-derived 4.4nF Y-cap leakage limit's exact arithmetic (§6)
  — order-of-magnitude discrepancy against the function's own stated
  default. Investigated further per coordinator request, see §10 Addendum
  item 4 — narrowed, but the primary standard text was not accessed, so
  the exact correct number remains UNVERIFIED.
- `check_y_cap_placement`'s PE-connection-distance leg on the real board —
  no discrete PE-stud component exists to supply a real position (§8).
- Whether `check_filter_component_order`/`check_filter_signal_flow`/
  `check_cm_choke_placement`'s raw x-order findings on the real board (§8)
  represent genuine placement defects or artifacts of a non-collinear 2D
  layout not matching this checker's left-to-right assumption — the
  `check_cm_choke_placement` finding specifically looks like the latter
  (contradicted by topology), the `check_filter_component_order` findings
  were not independently corroborated either way.
- Why `test_emi_filter.py`'s tests were failing (not skipped) continuously
  before this change while `test_ground_plane.py`'s were properly skipped
  (§7) — noted, not investigated further (outside this task's scope).

---

## 10. Addendum (2026-07-26) — coordinator review, one finding overturned

The coordinator merged the work above (57 passed / 4 skipped verified in
the broader `emc/` suite at merge time), confirmed the zero-routed-copper /
zero-zones findings independently, and flagged that this document's MOV
finding was very likely a wrong requirement, not a wrong design. This
section records the research done in response and what changed.

### Item 1: `check_mov_placement`'s original requirement was backwards — corrected

**Claim investigated:** the design has `elec/src/modules.ato:658-659`:
`fuse.p2 ~ mov.p1`, `mov.p2 ~ ac_n` — the MOV is wired *downstream* of the
fuse. `check_mov_placement`'s original docstring required the opposite
("at AC input, before or parallel to fuse"), and the original version of
this document reported the real board as a `MOV-001` violation on that
basis.

**Research performed** (WebSearch/WebFetch against public engineering
literature; UL 1449 and IEC 61051-1 full primary text are both paywalled
and were **not** accessed — this is secondary-source corroboration, marked
as such, not a primary-standard citation):

- A Digikey engineering article on meeting IEC 60335 power-supply
  requirements, citing a commercial reference design (PSK-10D-12-T):
  *"a 2A/300V slow-blow fuse is provided upfront, along with a metal oxide
  varistor (MOV)... this sequential arrangement means the fuse sits between
  the AC source and the MOV, protecting the entire circuit including the
  varistor itself."* — fuse upstream, MOV downstream, matching this
  design's wiring exactly.
- General MOV-fusing / fire-safety literature (multiple independent
  sources: an AllPCB article on MOV aging, general surge-protection patent
  literature, industry articles on MOV thermal-runaway failure): MOVs'
  characteristic end-of-life failure mode is a low-resistance short, not an
  open circuit, and the standard mitigation is external fusing positioned
  so the fuse's current path includes the MOV, so a shorted MOV is
  interrupted rather than left drawing sustained fault current from the
  mains.
- No source found in this research recommended the reverse arrangement
  (MOV upstream of / in parallel ahead of the fuse with nothing downstream
  to interrupt a short).

**Conclusion: the coordinator's reasoning is correct, and the original
requirement was backwards.** Corrected:

- `check_mov_placement`'s docstring and logic (`emi_filter.py`): now
  requires the MOV at or after (never before) the fuse; flags `MOV-001` on
  the opposite condition from before.
- `_CANONICAL_ORDER` (shared by `check_filter_signal_flow` and
  `check_filter_component_order`): `FUSE` now precedes `MOV`, was the
  reverse.
- `check_filter_component_order`'s and `check_filter_signal_flow`'s
  docstrings updated to match.
- Tests updated: `correct_filter_layout` fixture (FUSE/MOV positions
  swapped), `TestMOVPlacement.test_mov_at_input` (fixture swapped),
  `test_mov_after_fuse_fails` renamed to `test_mov_before_fuse_fails` with
  the fixture flipped to the new failure condition.
- The real-board integration test
  (`test_temper_board_emi_filter_compliance`) now asserts
  `check_mov_placement` **PASSES** on the real board — re-run confirms
  `passed=True`, zero `MOV-001` violations. The "violation" reported in
  the original version of this document is retracted: it was a defect in
  the validator's requirement, not in the board.
- Full suite re-verified after the correction: `emc/test_emi_filter.py` +
  `emc/test_ground_plane.py` — **42 passed, 2 skipped** (unchanged from
  before the correction; the fix only changed *which* fixtures encode the
  correct/incorrect cases, not the pass/fail counts).

This is exactly the failure mode flagged in the original task brief
("a validator that fails a correct mains design is worse than no
validator: it trains people to ignore safety output") — caught here
because the coordinator checked a specific finding against domain
knowledge rather than trusting the tool's output, which is the right
instinct and the reason this addendum exists.

### Item 2: struck the 76.2%/616 figures

Confirmed and corrected in §8 above — the specific numbers are no longer
repeated in this document; only the fact that a larger, non-zero
routed-copper figure appeared elsewhere and did not describe this
committed artifact is noted, with a pointer to where it was corrected
(`docs/STRATEGY.md` commit `391ed5d3`).

### Item 3: topology-from-geometry inference is unsound in general

Reinforced in §8 above with an explicit statement rather than leaving it
implicit in the `check_cm_choke_placement` row's caveat alone.

### Item 4: the ~10x leakage-current discrepancy, investigated further

**Re-derivation, precisely (Python, not mental arithmetic — the same class
of error this task's own memory bank warns about):**

```
C = I / (2*pi*f*V)
I = 3.5 mA, f = 50 Hz, V = 250 V  ->  C = 44.56 nF   (10.1x the stub's 4.4nF default)
I = 0.75 mA (IEC 60335-1 Class I portable limit)      ->  C = 9.55 nF   (2.2x)
I = 1.35 mA (see below)                               ->  C = 17.2 nF   (3.9x)
```

**New research this round, specifically on which appliance-classification
touch-current figure actually applies to this product:**

- IEC 60335-1's Class I touch-current limits (via a Digikey article and
  corroborating search results) are **not a single number** — they differ
  by appliance category: 0.75mA for portable appliances, 3.5mA for
  *stationary motor-operated* appliances, and — the category that actually
  matters here — **"0.75mA or 0.75mA per kW rated input power, whichever
  is higher, up to a maximum of 5mA," for stationary *heating*
  appliances.**
- Temper is an induction cooktop: a stationary heating appliance (IEC
  60335-2-6, "particular requirements for stationary cooking ranges, hobs,
  ovens" — search results confirm induction hobs are explicitly in this
  Part 2-6's scope, not the portable-appliance Part 2-9), rated 1800W
  (1.8kW). Applying the per-kW formula: `0.75mA x 1.8kW = 1.35mA` (above
  the 0.75mA floor, well under the 5mA cap) — so **1.35mA, not 3.5mA, is
  the figure that plausibly applies to this specific product**, if the
  per-kW formula above is stated correctly (it was not independently
  confirmed against IEC 60335-1's primary text; secondary-source only).
- 1.35mA corresponds to ~17.2nF, not 44.6nF (the 3.5mA figure) and not
  4.4nF (the stub's default) — a third, different number, closer to the
  stub's own docstring citation of "3.5mA" in magnitude-of-error terms
  than to the stub's actual 4.4nF value, but matching neither exactly.

**Determination:** I cannot access IEC 60335-1's or IEC 60335-2-6's
primary text (both paywalled; not fetched) to confirm the exact applicable
number, so the precise correct capacitance ceiling remains
**UNVERIFIED**. What I can say with reasonable confidence from this
research: under *every* standard-category interpretation found (portable
0.75mA, stationary-heating-per-kW 1.35mA, or stationary-motor-operated
3.5mA), the real permitted Y-cap ceiling comes out **higher** than the
stub's 4.4nF default — by roughly 2x to 10x depending on category. That
means:

- The **direction** of the discrepancy is the safe one: `check_y_cap_placement`'s
  4.4nF default is, if anything, *more conservative* than any interpretation
  of the standard actually requires — not a validator that would pass a
  design the real standard would reject.
- I did **not** change the 4.4nF default. Touch-current limits are
  classification-dependent and safety-critical; picking a specific
  replacement number requires either primary-standard access or a
  qualified person's product-classification sign-off, neither of which
  this pass has. Changing it on secondary-source research alone would
  replace one unverified number with another unverified number.
- This differs from item 1: there, multiple independent sources agreed on
  one clear direction with no contradicting source, and the design's own
  wiring corroborated it. Here, the sources characterize a
  classification-dependent *family* of numbers (0.75mA / 1.35mA / 3.5mA
  depending on category) rather than one clear figure, and I could not
  independently confirm which category-specific formula is exactly right
  without the primary text. Flagged UNVERIFIED rather than guessed, per
  the task's own standing instruction.
- In this design specifically, the real Y-cap total (2.2nF, one cap) is
  comfortably under every candidate ceiling found (4.4nF through 44.6nF),
  so this ambiguity does not change today's real-board verdict — noted for
  whoever tightens or re-derives this default later.
