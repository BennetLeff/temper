# Safety Validators Implemented — REQ-SAFE-01 (clearance.py) / REQ-SAFE-02 (isolation.py)

<!-- provenance: commit=61967aa92b955094119b6ee9590ad1e7586bd18c dirty=UNKNOWN -->

**Date:** 2026-07-26
**Scope:** `packages/temper-placer/tests/requirements/validators/clearance.py` (3
stubs), `packages/temper-placer/tests/requirements/validators/isolation.py` (7
stubs). `emi_filter.py`, `ground_plane.py`, `schematic.py` untouched (owned by
another agent / deferred), per instruction.

---

## 0. Base verification

Started in a worktree whose HEAD was **behind**
`docs/methodology-loop-discipline` (a strict ancestor: `git merge-base
docs/methodology-loop-discipline HEAD` == `HEAD`) — missing the SELV
isolation redesign, the IEC 60335-1 critical-components doc, and
`scripts/assert-base.sh` itself. Rebased onto
`docs/methodology-loop-discipline` (clean rebase, no conflicts), then ran
`scripts/assert-base.sh docs/methodology-loop-discipline` → `ASSERT-BASE OK:
HEAD == docs/methodology-loop-discipline (104fd349384e279485a451f3948d6156a18af8dc)`,
exit 0. All work below is on top of that base.

---

## 1. Falsifiers, stated before implementing, and whether they fired

For each validator, the falsifier is the condition that would mean the
implementation inspects nothing and passes vacuously (the failure mode the
task explicitly warns against).

| Validator | Falsifier | Fired? |
|---|---|---|
| `check_domain_clearance` | Placement with two components 2mm apart, min_mm=3.0 → if `result.passed` is `True`, the check is inspecting nothing. | **Did not fire.** `TestDomainClearance::test_insufficient_clearance_fails` — returns `passed=False`, 1 violation. |
| `check_creepage_path` | Same 2mm fixture, min_mm=4.0 → if `passed` is `True`, vacuous. | **Did not fire.** `TestCreepagePath::test_insufficient_creepage_fails` passes. |
| `verify_iec60335_compliance` | Multi-domain placement with 2mm gaps across 3 domains, min matrix requirements 3-8mm → if `error_count < 2`, the matrix isn't being walked. | **Did not fire.** `test_multiple_violations_aggregated` gets `error_count >= 2` (actually produces many more, since every applicable matrix row fires). `test_all_boundary_types_checked` (new) additionally proves all 6 matrix rows and all 4 boundary strings are reachable — **did not fire.** |
| `check_isolation_slot` | Barrier with `slot_width=1.5`, `min_width_mm=2.0` → if `passed` is `True`, vacuous. | **Did not fire.** `test_main_hv_lv_barrier_insufficient_width` passes. |
| `check_no_traces_across_barrier` | Trace from (10,10) to (90,40) crossing a barrier at y=25 → if 0 violations, vacuous. | **Did not fire.** `test_trace_crossing_horizontal_barrier` / `_vertical_barrier` pass; the "near but not crossing" fixture correctly reports 0. |
| `check_ground_plane_split` | One rectangle spanning the full barrier x-range with no split → if 0 violations, vacuous. | **Did not fire.** New assertion in `test_unsplit_ground_plane` confirms 1 `GROUND_PLANE_NOT_SPLIT` violation; `test_proper_ground_plane_split` confirms the split case reports 0. |
| `check_clearance_distances` | Two components 5mm from a barrier requiring 10mm → if 0 violations, vacuous. | **Did not fire.** New assertions in `test_insufficient_clearance` confirm 2 violations (one per component), `test_sufficient_clearance` confirms 0 for the 30mm case. |
| `check_power_domain_separation` | A supply with `domain="SHARED"` and no isolation components → if 0 violations, vacuous. | **Did not fire.** New assertions confirm 1 `POWER_DOMAIN_NOT_SEPARATED` error; a second new test confirms the "2 real domains, no isolation components" case produces a `MISSING_ISOLATION_COMPONENTS` warning without failing `passed`. |
| `check_ucc21550_barrier` / `check_adum1250_barrier` | N/A — left `NotImplementedError`. Falsifier would be "returns a fabricated pass despite having no board data" — the whole point of leaving these unimplemented is to make that falsifier permanently unreachable. | N/A by design. |
| **Real-board falsifier** (clearance.py, end-to-end) | If `verify_iec60335_compliance` run against real component positions/domains reports 0 violations while a mains-side component (fuse) sits sub-mm from an SELV connector, the check is vacuous on the one input that matters most. | **Did not fire.** Reports 18 real violations (§5), worst case 0.836mm between F1 (fuse, MAINS) and J1 (fan connector, LV_CONTROL) against a 3-6mm requirement. |

---

## 2. Reused vs. written fresh

**Reused:**
- `packages/temper-placer/tests/requirements/validators/_geometry.py::_distance` —
  the existing Euclidean-distance helper already shared by `bypass_caps.py`,
  `layout_review.py`, `switching_nodes.py`, `pick_and_place.py`. Used by both
  files for every point-to-point measurement instead of hand-rolling
  `math.dist`/`math.hypot` again.
- `IEC60335_REQUIREMENTS` (the requirement matrix already present in
  `clearance.py`, lines 63-95) — not modified. Treated as the pre-existing
  SSOT for clearance/creepage figures; see §4 for provenance/verification
  status of those specific numbers (I did not author them and did not find a
  cited source in-repo for them, so their provenance is noted but not
  re-derived here).
- `temper_placer.io.kicad_parser.parse_kicad_pcb` (real-board fixture) — the
  canonical, most-used PCB loader in this repo. Not re-implemented.
- `RC0603FR-0710KL` etc. identity lookups via `elec/build/default.csv` (per
  the task's own footprint-aliasing warning) rather than trusting
  `default.net`'s embedded footprint fields, for the component identities
  quoted in §5.

**Not reused, and why:**
- `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py::verify_clearance`
  operates on `RoutingResults.compiled_routes` (routed-copper segment/via
  geometry) — a fundamentally different input shape from this suite's
  `placement` dicts (bare component positions, no routing). Its
  `_segment_to_segment_dist`/`_point_to_segment_dist` machinery solves a
  segment-vs-segment problem this suite doesn't have (components here are
  points, not routed traces with width). Calling it would require inventing
  synthetic `RoutingResults` from `placement`, which is more indirection
  than writing the (much simpler) point-distance check directly against the
  data actually given. Its unified-clearance-engine dependency
  (`clearance_engine.get_clearance`, net-class based: HV/GND/POWER/SIGNAL)
  is also a different classification axis than this suite's
  `VoltageDomain` enum (MAINS/DC_BUS/BOOTSTRAP/LV_CONTROL/ISOLATED) — not a
  drop-in match without a translation layer that didn't already exist.
- `packages/temper-drc-rs/src/rules/safety/isolation.rs`,
  `routing/isolation_barrier.rs`, `routing/isolation_slot.rs` — these are
  registered Rust DRC rules operating on `BoardState`/`ConstraintSet` (real
  `geo::Polygon`/`geo::Line` geometry: zones, traces, copper polygons). No
  PyO3 binding exposes them to Python (only `verify_route_clearance` is
  bound, per `clearance_check.py`), and this validator suite's `barrier`/
  `traces`/`ground_planes` arguments are plain dicts, not board geometry.
  **The check semantics were matched deliberately** even though the code
  wasn't reused:
  - `check_isolation_slot`'s default `min_width_mm=2.0` matches
    `isolation_slot.rs`'s `MIN_SLOT_WIDTH_MM` constant exactly.
  - `check_no_traces_across_barrier`'s crossing test is the same intent as
    `isolation_barrier.rs`'s `check_trace_barrier_intersections`
    (line-vs-trace intersection), implemented against an infinite line
    through `barrier["position"]` here vs. a finite `geo::Line` built from
    real `barrier.y_span` there.
  - Each function's docstring states this correspondence and the precise
    difference, per the task's instruction ("if they differ, say precisely
    how").
- A second, independent creepage-path tracer was **not** written. Per the
  task's explicit warning ("two divergent creepage implementations on a
  mains appliance is a worse outcome than one unimplemented stub"),
  `check_creepage_path` uses the same straight-line distance as
  `check_domain_clearance`, documented as a conservative lower bound (see
  §3), rather than attempting a second slot-aware surface-path algorithm
  that could diverge from the Rust engine's.

---

## 3. Per-validator status

### clearance.py (3/3 implemented)

| Function | Status | Notes |
|---|---|---|
| `check_domain_clearance` | **Implemented** | Straight-line distance between all cross-domain component pairs (or same-domain pairs when domain_a==domain_b). |
| `check_creepage_path` | **Implemented, with a documented approximation** | Uses the same straight-line distance as clearance. This is an exact measure of *clearance* but only a conservative *lower bound* on *creepage* (true surface path length ≥ straight-line distance, by the triangle inequality, since `placement` carries no board-outline/slot polygon to trace a path around). Consequence: this can produce **false-positive** creepage violations near a slot that lengthens the real path, but can **never mask** a real creepage violation. Documented in the function's docstring with a pointer to the real Rust isolation-slot rule for board-geometry-aware creepage. |
| `verify_iec60335_compliance` | **Implemented** | Iterates every `(domain_a, domain_b, insulation_type)` row in `IEC60335_REQUIREMENTS`, running both clearance and creepage checks per row, annotating each violation's `boundary`/`insulation_type`. Proven by `test_all_boundary_types_checked` to actually reach every row (not a hardcoded subset). |

### isolation.py (5/7 implemented, 2 faithfully unimplemented)

| Function | Status | Notes |
|---|---|---|
| `check_isolation_slot` | **Implemented** | Scalar `slot_width < min_width_mm` comparison. |
| `check_no_traces_across_barrier` | **Implemented** | Infinite-line sign-change crossing test (see §2). |
| `check_ucc21550_barrier` | **Faithfully unimplemented** | Signature takes only `driver_position: (x, y)`. None of its 3 stated requirements (no traces under the transformer footprint, ground-plane cutout, separate VCCI/VDDA/VDDB power domains) can be evaluated from a single point — there is no trace list, ground-plane geometry, or net-assignment argument. Implementing this faithfully needs, at minimum, the same kinds of inputs `check_no_traces_across_barrier`/`check_ground_plane_split`/`check_power_domain_separation` already receive; the gap is the function's own signature, not missing logic. Raises `NotImplementedError` with this reasoning inline. |
| `check_adum1250_barrier` | **Faithfully unimplemented** | Same reasoning: signature takes only `isolator_position: (x, y)`, with no component/clearance data, ground-plane geometry, or power-supply domain data to check its 3 stated requirements (10mm clearance, ground-plane split, separate power supplies) against. |
| `check_ground_plane_split` | **Implemented** | Flags any ground-plane rectangle whose span along the barrier's axis strictly straddles the barrier line. |
| `check_clearance_distances` | **Implemented** | Distance from each component to each barrier's position, against `max(min_clearance_mm, barrier["clearance_mm"])`. |
| `check_power_domain_separation` | **Implemented** | Flags a `None`/`"SHARED"` domain directly (error); flags 2+ distinct domains with no `isolation_components` as a warning (doesn't fail `passed`). |

**Why 2 were left unimplemented, restated plainly:** both functions' call
sites in the test suite pass a bare tuple — `check_ucc21550_barrier((75.0,
30.0))`, `check_adum1250_barrier((25.0, 50.0))` — with no other argument.
Every other function in this suite that touches similar concerns
(trace-crossing, ground-plane geometry, clearance-to-barrier, power-domain
data) is *given* that data as an argument. These two are not. Writing a
function body that returns `IsolationResult(passed=True, violations=[])`
unconditionally would be indistinguishable, to a caller, from a real check
that happened to find nothing — exactly the "inspects nothing and passes"
failure mode this task instructs against. Left raising `NotImplementedError`
with the specific missing-data explanation inline, per the task's explicit
permission to do so.

---

## 4. IEC assumptions and what's UNVERIFIED

- **`IEC60335_REQUIREMENTS` matrix values** (3.0/4.0mm basic and
  6.0/8.0mm reinforced clearance/creepage for MAINS↔LV_CONTROL and
  DC_BUS↔LV_CONTROL; 0.5/1.0mm functional within LV_CONTROL) were **already
  present in `clearance.py` before this pass** — not authored here. They are
  broadly consistent with IEC 60664-1 Table F.2/F.4-style clearance/creepage
  figures for basic vs. reinforced insulation at pollution degree 2,
  material group IIIa, working voltages in the low-hundreds-of-volts range
  (which matches this design's ≤340V DC bus and 240VAC mains) — but I did
  not independently re-derive them from a specific table cell/edition, and
  no in-repo citation for these exact numbers was found. **UNVERIFIED
  provenance** — flagged rather than re-asserted as correct. The
  pollution-degree/material-group/overvoltage-category assumptions implicit
  in the numbers were not stated in the source and are not stated here as
  confirmed; if this matrix needs certification-grade backing, it needs a
  cited table lookup this pass did not do.
- **`min_width_mm=2.0`** default in `check_isolation_slot` — cross-checked
  (not independently derived) against
  `packages/temper-drc-rs/src/rules/routing/isolation_slot.rs`'s
  `MIN_SLOT_WIDTH_MM = 2.0` constant, which matches exactly. That Rust
  constant's own provenance is not documented in its file either — so this
  is corroboration between two parts of this codebase, not an independent
  standards citation. **UNVERIFIED against an external IEC table.**
- **`min_clearance_mm=10.0`** default in `check_clearance_distances` and
  the ADUM1250 docstring's "10mm clearance" — these are pre-existing
  defaults in the stub signatures (not introduced by this pass) and were
  not independently re-derived from a standard.
- **Real-board net→domain classification** (§5): asserted directly from
  `docs/hardware/SELV_ISOLATION_REDESIGN.md` and a direct read of
  `elec/build/default.net`, not invented. `pe` is **UNVERIFIED / absent**:
  it does not appear as a named net anywhere in the freshly-built
  `default.net` (confirmed by direct grep, zero matches), consistent with
  `IEC60335_CRITICAL_COMPONENTS.md`'s finding that no physical mains inlet/PE
  connector is instantiated in `elec/src` — so `pe` never resolves to a
  pad-bearing pin. `VoltageDomain.ISOLATED` is likewise never populated by
  the real-board fixture: no single net name in this design corresponds to
  "the floating side of a declared isolator" the way the enum intends, so
  the `(MAINS, ISOLATED, REINFORCED)` matrix row is checked against the real
  board but always finds zero candidate components — an honest gap in
  coverage, not a compliance claim.
- **`pcb/temper.kicad_pcb` is stale relative to the current schematic
  source** (verified directly, not assumed): its own embedded net list still
  has `+340V_BUS` (the SELV redesign renamed this to `+170V_BUS`) and has
  **no `gnd`, `ZCD_ISO`, or `pe` net at all** — its SELV-side nodes are still
  the pre-merge fragmented per-instance micro-nets. The real-board fixture
  works around this by joining PCB positions to `default.net` connectivity
  by reference designator (a ref is stable across a net rename; a net name
  is not) — see `_real_board_fixture.py`'s module docstring for the full
  reasoning. 149 of 167 `default.net` components exist in the PCB (18 not
  yet placed, consistent with "76.2% routed").
- **Isolation.py's 5 implemented validators were proven correct against
  fixtures only, not run against real board geometry in this pass.** Unlike
  clearance.py, I did not build a real-trace/real-ground-plane/real-barrier
  data-extraction pipeline for `check_no_traces_across_barrier`,
  `check_ground_plane_split`, `check_isolation_slot`, or
  `check_clearance_distances`. This is a genuine scope limitation, stated
  plainly rather than glossed over. It is corroborated, not just excused, by
  a fact surfaced while researching reuse targets: the project's own
  `DrcRatchet._run_rust_drc` (the thing that actually invokes the Rust DRC
  engine, including `isolation.rs`/`isolation_barrier.rs`/`isolation_slot.rs`,
  against the real board) currently builds its `constraints_dict` with
  `zones`/`isolation_barriers` left at empty defaults — meaning even the
  Rust engine's isolation-barrier/slot rules are not actively exercised
  against real barrier geometry today either. This is a pre-existing,
  project-wide gap in barrier-geometry availability, not something specific
  to this validator suite, and not something this pass closed.

---

## 5. Real-board violations found (clearance.py, `verify_iec60335_compliance`)

Real-board fixture: `packages/temper-placer/tests/requirements/safety/_real_board_fixture.py`.
Built from `pcb/temper.kicad_pcb` (positions) joined to a freshly-generated
`elec/build/default.net` (`make netlist`, exit 0) by reference designator.
110-112 components matched onto a classified domain net (exact count is
112 with all 10 requested nets present — see stats below); 149 total
components in the PCB.

```
STATS: {
  'pcb_components': 149,
  'netlist_refs_on_classified_nets': 127,
  'matched_components_in_placement': 112,
  'classified_nets_present': ['+15V', '+170V_BUS', '+3V3', 'DC_BUS_RTN',
                               'PWR_RTN', 'ZCD_ISO', 'ac_l', 'ac_n', 'gnd', 'zcd'],
  'classified_nets_requested_but_absent': []
}
```

**`verify_iec60335_compliance(placement, voltage_domains)`: `passed=False`,
18 violations, all severity `error`.** Zero violations on the
`(MAINS, LV_CONTROL, BASIC)`/`(DC_BUS, LV_CONTROL, BASIC)` 3mm/4mm rows
except the F1/J1 pair below — the board is not egregiously bad, but it does
not meet the reinforced-insulation (6mm/8mm) tier between the mains/DC-bus
domain and the SELV control domain in 16 of 18 cases.

By boundary/insulation type:

| Boundary | Insulation | Count | Distance range |
|---|---|---|---|
| MAINS↔LV_CONTROL | basic | 2 | 0.836mm (both clearance+creepage, same pair) |
| MAINS↔LV_CONTROL | reinforced | 6 | 0.836mm – 7.848mm |
| DC_BUS↔LV_CONTROL | reinforced | 10 | 5.410mm – 7.832mm |

Full list, sorted by measured distance (all identities below confirmed via
`elec/build/default.csv`, the authoritative identity source, not `.net`'s
footprint-derived fields):

1. **F1 (Schurter 0034.3129, mains fuse) ↔ J1 (PinHeader 1x02, `thermal.j_fan`
   fan-power connector, SELV/gnd)** — **0.836mm** clearance, required 3.0mm
   (basic).
2. Same pair, **0.836mm** creepage, required 4.0mm (basic).
3. Same pair, **0.836mm** clearance, required 6.0mm (reinforced).
4. Same pair, **0.836mm** creepage, required 8.0mm (reinforced).
5. **U5 (IKW40N120H3 IGBT, half-bridge) ↔ U18 (TLV3201 comparator, SELV)** —
   **5.410mm** clearance, required 6.0mm (reinforced).
6. Same pair, **5.410mm** creepage, required 8.0mm (reinforced).
7. **R8 (RC0603FR-0710KL, 10kΩ) ↔ R54 (RC0603FR-0710KL, 10kΩ — the OVP-01
   divider's bottom leg, `r_div_bot`, confirmed on `gnd`)** — **6.904mm**
   creepage, required 8.0mm.
8. **C2 (EKMQ251VSN182MA50S electrolytic) ↔ C20 (100nF 0603 bypass cap)** —
   **6.947mm** creepage, required 8.0mm.
9. **C3 (same family as C2) ↔ C30 (100nF 0603 bypass cap)** — **6.947mm**
   creepage, required 8.0mm.
10. **R58 (RC1206FR-07510KL, 510kΩ — matches
    `IEC60335_CRITICAL_COMPONENTS.md`/`SELV_ISOLATION_REDESIGN.md`'s
    "second, independent divider" / `r_adc_top`, confirmed on `+170V_BUS`)
    ↔ R59 (RC0603FR-0710KL, 10kΩ — `r_adc_bot`, confirmed on `gnd`)** —
    **6.960mm** creepage, required 8.0mm. **This is the second of the two
    "STILL CROSSING — not fixed" OVP dividers from
    `SELV_ISOLATION_REDESIGN.md` §4 rows 3-4** — independently confirmed
    here at the PCB layout level, not just at the netlist-topology level.
11. **L1 (TDK B82726S2163N030 common-mode choke) ↔ R1 (RSF100JB-73-39R 39Ω,
    `power_in.r_relay_drop`, SELV gate-driver resistor)**, MAINS-side pairing
    — **7.145mm** creepage, required 8.0mm.
12. Same L1/R1 pair, DC_BUS-side pairing (L1 legitimately touches both
    `ac_n` and `PWR_RTN`/`dc_bus.gnd_ref`, per
    `SELV_ISOLATION_REDESIGN.md`'s own description of the CMC) — **7.145mm**
    creepage, required 8.0mm.
13. **R7 (RC1206FR-07220KL, 220kΩ — with R6, forms the ~440-450kΩ raw ZCD
    top divider, `r_zcd_top1`/`r_zcd_top2`, matching
    `IEC60335_CRITICAL_COMPONENTS.md`'s "450kΩ path" description) ↔ R66
    (RC0603FR-073K32L, 3.32kΩ)** — **7.339mm** creepage, required 8.0mm.
14. **R58 (510kΩ, `r_adc_top`) ↔ R43 (ERA-3AEB103V, 10kΩ precision)** —
    **7.561mm** creepage, required 8.0mm.
15. **R6 (220kΩ, `r_zcd_top1`) ↔ R59 (10kΩ, `r_adc_bot`)** — **7.770mm**
    creepage, required 8.0mm.
16. **R6 (220kΩ) ↔ R60 (10kΩ)** — **7.770mm** creepage, required 8.0mm.
17. **R58 (510kΩ) ↔ R44 (RC0603FR-07100KL, 100kΩ)** — **7.832mm** creepage,
    required 8.0mm.
18. **R6 (220kΩ) ↔ R46 (ERA-3AEB104V, 100kΩ)** — **7.848mm** creepage,
    required 8.0mm.

**Read on this:** the worst finding (#1-4, F1↔J1 at 0.836mm) is a genuine,
independent finding not previously called out in
`SELV_ISOLATION_REDESIGN.md` or `IEC60335_CRITICAL_COMPONENTS.md` — a mains
fuse sitting sub-mm from a user-touchable fan-power connector. Findings
#7 and #10 are direct, PCB-layout-level confirmation of the two
already-documented "STILL CROSSING" OVP dividers from
`SELV_ISOLATION_REDESIGN.md` §4 (rows 3-4): not only are they resistively
connected across the barrier (as that document establishes from netlist
topology), their physical layout also fails the reinforced creepage margin
that a proper isolated redesign (Option A/B in that document) would need to
meet. The remaining 14 are reinforced-tier-only creepage shortfalls
(5.4-7.8mm against an 8mm requirement) — real, but each is within about
2mm of compliant, consistent with a board that is 76.2% routed and was laid
out before or during the SELV domain float rather than against a
verified 8mm-reinforced-creepage rule.

**Not tuned away:** no threshold in `IEC60335_REQUIREMENTS` was changed to
reach this result, no boundary was excluded, and no component was
allowlisted. `test_temper_board_clearance_compliance` is marked
`@pytest.mark.xfail(strict=True, ...)` with this exact violation count in
the reason string — it fails (in the "this assertion is false" sense) every
time it runs, and stays visible rather than silently skipped; if the board
is ever re-laid-out to close these gaps, the xfail will unexpectedly pass
(`XPASS`) and, because `strict=True`, that itself becomes a test failure
forcing the marker's removal.

---

## 6. Test counts: before / after

Measured with `python -m pytest <path> -v`, counts read from the printed
per-test lines and the summary line, not from exit codes alone.

| Suite | Collected | Passed | Failed | Skipped | XFailed |
|---|---|---|---|---|---|
| `test_clearance.py`, **before** | 23 | 0 | 0 | 23 | 0 |
| `test_clearance.py`, **after** | 23 | 22 | 0 | 0 | 1 |
| `test_isolation.py`, **before** | 35 | 13 | 22 | 0 | 0 |
| `test_isolation.py`, **after** | 31 | 31 | 0 | 0 | 0 |
| **Combined, before** | 58 | 13 | 22 | 23 | 0 |
| **Combined, after** | 54 | 53 | 0 | 0 | 1 |

The collected-count delta (58 → 54, net −4) is not a coverage loss: 5 stale
`TestNotImplementedErrors` methods in `test_isolation.py` were removed
because the functions they tested (`check_isolation_slot`,
`check_no_traces_across_barrier`, `check_ground_plane_split`,
`check_clearance_distances`, `check_power_domain_separation`) are now
implemented and have their own dedicated positive/negative tests (which
already existed as `TestCheckIsolationSlot` etc., previously failing with
`NotImplementedError`, now passing) — keeping the "raises NotImplementedError"
assertion for an implemented function would be actively wrong, not
conservative. 2 new tests were added (`test_all_boundary_types_checked`
rewritten from an unconditional `pytest.skip()` into a real assertion, and
`test_multiple_domains_without_isolation_components_warns`), and 1 new
real-board test (`test_temper_board_clearance_compliance`, rewritten from
an unconditional `pytest.skip()`). Net: −5 (removed) +1 (new
power-domain test) in isolation, and 0 net change in clearance
(2 skips converted to 1 real test + 1 real xfail test, same 2 method
names). No test was deleted to hide a result; every removal corresponds to
an assertion that became actively false once its target function was
implemented.

**Full breakdown, zero ambiguity:** after this pass, running both files
together: **54 collected, 53 passed, 1 xfailed, 0 skipped, 0 failed, 0
errors.** The 1 xfailed is `test_temper_board_clearance_compliance` — a
real, tracked, currently-true statement that the real board has 18
REQ-SAFE-01 violations (§5), not a flaky or ambiguous result.

---

## 7. Commits

- `feat(safety): implement REQ-SAFE-01 clearance/creepage validators` —
  clearance.py's 3 functions, the `str`-mixin enum fix, and the real-board
  fixture.
- `feat(safety): implement REQ-SAFE-02 isolation-barrier validators` —
  isolation.py's 5 implemented + 2 faithfully-unimplemented functions, and
  the test-file corrections/strengthening described in §6.
