---
type: feat
origin: docs/brainstorms/2026-07-08-4-layer-functional-stackup-requirements.md
contract: docs/brainstorms/2026-07-08-gate-contract.md
status: active
date: 2026-07-08
workstream: W2
depth: deep
depends_on: [W0, W1]
---

# W2 — 4-Layer Functional Stackup

## Summary

Turn the four copper layers from interchangeable routing planes into a
*functional* stackup: F.Cu (signal + high-current power + gate drive + USB
diff-pair), In1.Cu (solid GND reference plane), In2.Cu (isolated power-domain
pours), B.Cu (signal + gate drive + thermal pour). The work adds (1) a
deterministic JLCPCB **JLC04161H-7628** stackup definition, (2) a per-net-class
`layer` assignment wired through `route_pcb()`, (3) an **IPC-2152** minimum-width
calculator that sizes each net from its expected current with internal-layer
derating, (4) power-domain pours on In2.Cu plus a thermal-via array under the
Q1/Q2 IGBTs, (5) controlled-impedance USB diff-pair routing on F.Cu referenced
to In1.Cu, and (6) a `StackupGate` conforming to the shared gate contract that
fails closed on reference-plane splits and IPC-2152 current-density violations.

The plan builds only on the *existing* router_v6 stackup infrastructure —
`stage0_data.StackupInfo`/`LayerInfo`, `core/board.LayerStackup`,
`layer_assignment.py`, `trace_width_assignment.py`, `reference_plane_constraints.py`,
`differential_pair_constraints.py`, `thermal_relief.py`, and
`deterministic/stages/power_plane.py` — rather than introducing a parallel model.

---

## Problem Frame

The router treats F.Cu/In1.Cu/In2.Cu/B.Cu as four equivalent A* layers. Three
concrete gaps make the current behaviour electrically wrong for the temper
board:

1. **Stackup is generic, not JLC.** `core/board.LayerStackup.default_4layer()`
   (board.py:259) hard-codes F.Cu at **2oz** and inner layers at **1oz** with no
   dielectric heights. The JLC04161H-7628 offering is **1oz outer / 0.5oz inner**
   with a 0.2mm prepreg (F.Cu↔In1.Cu) and a 1.1mm core (In1.Cu↔In2.Cu). Without
   the real dielectric heights and copper weights, both impedance and IPC-2152
   ampacity are computed from the wrong cross-section.

2. **No net→layer contract.** `configs/netclass_rules.yaml` has no `layer` field.
   `router_v6/layer_assignment.py` assigns layers by **regex on net names** with a
   catch-all that lets every net use all four layers (`allowed_layers={L1..L4}`),
   so a B.Cu signal can hop onto In2.Cu (a power plane) and cross a reference-plane
   split. `route_pcb()` (adapter.py:373) never passes any layer constraint into
   the pipeline.

3. **Widths are string-heuristics, not current-based.**
   `router_v6/trace_width_assignment.py._determine_trace_width` picks a width from
   substrings (`AC_`, `GND`, `GATE`); it never consults the 16A/10A/2A per-net
   currents. `core/ipc2221.py` only computes the *forward* map (width→current) and
   uses the more-conservative IPC-2221 curve — there is no *inverse* IPC-2152
   `current → minimum width` sizing, and no internal-layer derating applied per
   net's assigned layer.

Additionally, the enclosing **gate contract**
(`docs/brainstorms/2026-07-08-gate-contract.md`) requires every routing-stage
checker to be a three-state (`CLEAN`/`VIOLATIONS`/`UNMEASURED`) fail-closed
`Gate`. W2 owes a `StackupGate` that measures reference-plane integrity and
current density and never reports a false-clean when it cannot measure.

### Naming / model reconciliation (decide once, up front)

Two layer models coexist and must be unified so the `layer` field is
unambiguous:

- `stage0_data.LayerInfo.index` and `deterministic/stages/power_plane.py` use
  **KiCad indices 0=F.Cu, 1=In1.Cu, 2=In2.Cu, 3=B.Cu**.
- `router_v6/layer_assignment.Layer` uses an enum **L1_TOP=1 … L4_BOT=4**.

**Decision:** the SSOT `layer` value in YAML is the **KiCad layer name**
(`F.Cu`/`In1.Cu`/`In2.Cu`/`B.Cu`), matching `board.STANDARD_LAYER_ORDER` and the
`2026-06-23-008 layer-names-consolidation` plan. A single
`layer_name → index → Layer` mapping helper (U2) is the only place the two
numbering schemes meet.

---

## Requirements → Units

| Req | Title | Unit(s) |
|-----|-------|---------|
| R1 | Stackup definition (JLC04161H-7628) | U1 |
| R2 | Net-to-layer assignment | U2 |
| R3 | IPC-2152 trace widths | U3 |
| R4 | Power plane pours + thermal | U4 |
| R5 | Via strategy | U4 |
| R6 | USB differential pair | U5 |
| (contract) | StackupGate | U6 |

---

## Implementation Units

### U1. JLC04161H-7628 stackup definition module

- **Goal:** A single deterministic source of truth for the physical stackup —
  layer order, copper weight (oz + µm), dielectric material/height/εr — that both
  the router (`StackupInfo`) and the board model (`LayerStackup`) resolve from,
  matching the JLCPCB JLC04161H-7628 4-layer offering.
- **Requirements:** R1
- **Dependencies:** None (foundation for U2–U6).
- **Files:**
  - `packages/temper-placer/configs/stackup_jlc04161h_7628.yaml` — **new.** Physical
    stackup spec (copper weights, dielectric heights, εr, loss tangent, total
    1.6mm).
  - `packages/temper-placer/src/temper_placer/router_v6/stackup_config.py` — **new.**
    Loader that parses the YAML into `stage0_data.StackupInfo`
    (`LayerInfo` + `DielectricInfo`) with a `JLC04161H_7628` module constant.
  - `packages/temper-placer/src/temper_placer/core/board.py` — add
    `LayerStackup.jlc04161h_7628()` classmethod alongside `default_4layer()`
    (board.py:259) with the correct **1oz outer / 0.5oz inner** copper weights.
  - `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py` — extend
    `LayerInfo` with an optional `copper_oz: float | None` and
    `StackupInfo.get_prepreg_between(a, b)` helper for the impedance/ampacity
    consumers (U3, U5). Keep existing fields/back-compat.
- **Approach:**
  - Encode the Key Decision verbatim: total 1.6mm; F.Cu 1oz (35µm) → 0.2mm prepreg
    → In1.Cu 0.5oz (17µm) → 1.1mm core → In2.Cu 0.5oz (17µm) → 0.2mm prepreg →
    B.Cu 1oz (35µm). Materials FR-4, εr ≈ 4.2 (prepreg 7628) / 4.5 (core); loss
    tangent 0.02 as documented defaults.
  - Populate `LayerInfo.thickness_um` from the copper weight and `layer_type`:
    `F.Cu`/`B.Cu` → `signal`, `In1.Cu` → `plane` (`plane_net="GND"`), `In2.Cu` →
    `plane` (`plane_net` left `None` at the stackup level because In2.Cu carries
    *multiple* domain pours — the per-domain pours are U4).
  - `jlc04161h_7628()` mirrors `default_4layer()` shape
    (`Layer(name, layer_type, copper_weight, is_routable)`) so all existing
    consumers keep working; **In1.Cu/In2.Cu remain `is_routable=False`** per the
    "no signal net on In2.Cu" requirement (R2).
  - **Do not** delete or repoint `default_4layer()` — the `2026-06-30-001
    4-layer-enforcement` invariant asserts the canonical 4 layer *names*, which
    the JLC stackup preserves; changing only weights/dielectrics keeps that gate
    green.
- **Patterns to follow:** `LayerStackup.default_4layer()` classmethod shape;
  `StackupInfo`/`LayerInfo`/`DielectricInfo` dataclasses in stage0_data.py;
  YAML-config + loader pattern of `configs/netclass_rules.yaml`.
- **Test scenarios:**
  - Loader yields 4 `LayerInfo` with names `F.Cu/In1.Cu/In2.Cu/B.Cu`, weights
    `1/0.5/0.5/1` oz, and 3 `DielectricInfo` (0.2/1.1/0.2 mm) summing (with copper)
    to 1.6mm ± tolerance.
  - `get_prepreg_between("F.Cu","In1.Cu")` returns the 0.2mm prepreg (drives the
    90Ω USB calc in U5).
  - `LayerStackup.jlc04161h_7628()` passes the existing canonical-4-layer invariant
    in `core/test_board.py`.
  - `StackupInfo.get_reference_plane(0)` (F.Cu) returns In1.Cu (index 1).
- **Verification:** `uv run pytest packages/temper-placer/tests -k "stackup and jlc"`.

---

### U2. Net-to-layer assignment from the SSOT

- **Goal:** Every one of the 9 net classes carries an explicit `layer` (or
  `allowed_layers`) assignment sourced from YAML, deterministically resolved per
  net, and threaded into `route_pcb()` so the A* search cannot place a signal net
  on a reference plane.
- **Requirements:** R2
- **Dependencies:** U1.
- **Files:**
  - `packages/temper-placer/configs/netclass_rules.yaml` — add a `layer` /
    `allowed_layers` key to each of the 9 classes (`ACMains`, `HighVoltage`,
    `HighCurrent`, `Signal`, `GND`, `Power`, `GateDrive`, `HighSpeed`,
    `FinePitch`). Encode the R2 table.
  - `packages/temper-placer/src/temper_placer/router_v6/layer_assignment.py` —
    add a `layer_assignments_from_netclass(design_rules, stackup) ->
    dict[str, LayerAssignment]` path that resolves each net's class → its layer(s),
    plus a `layer_name_to_enum` / `_to_index` mapping helper. Keep the existing
    regex `DEFAULT_LAYER_CONSTRAINTS` as fallback only.
  - `packages/temper-placer/src/temper_placer/router_v6/adapter.py` — in
    `route_pcb()` (adapter.py:373) resolve netclass layer assignments from
    `design_rules` + stackup and pass them into `RouterV6Pipeline` (new
    `layer_constraints=` kwarg).
  - `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — accept and
    honour `layer_constraints` in `RouterV6Pipeline.__init__`/`run` so the A* grid
    restricts each net to its allowed layers (In1.Cu/In2.Cu excluded for signals).
- **Approach:**
  - Encode the R2 table as the layer field. Classes that legitimately span both
    signal layers (`Signal` on F.Cu **and** B.Cu) use `allowed_layers: [F.Cu, B.Cu]`
    with a `preferred`; single-layer classes use one value. In2.Cu appears in **no**
    signal class's `allowed_layers` — the power rails reach In2.Cu only as pours
    (U4), enforcing "no signal net on In2.Cu."
  - The resolver walks `design_rules.net_class_assignments` (net→class) then
    `class→layer`, producing a `LayerAssignment` keyed by net name. Nets with no
    class fall back to the existing catch-all (`B.Cu` preferred).
  - Reuse `LayerAssignment`/`LayerConstraint` dataclasses; the new resolver
    produces the same output type `assign_layers()` already returns, so downstream
    consumers are unchanged.
  - **Layer numbering:** the one mapping helper converts YAML names → KiCad index
    (for the grid) and → `Layer` enum (for existing enum consumers).
- **Patterns to follow:** `design_rules.get_rules_for_net()` (stage0_data.py:103)
  class-lookup pattern; `assign_layers()` return contract; YAML SSOT of
  `netclass_rules.yaml`.
- **Test scenarios:**
  - Each of the 9 classes resolves to exactly the layers in the R2 table; every
    net in the temper netlist gets exactly one primary layer.
  - No signal net (any class except GND/power-rail pours) is allowed on In2.Cu.
  - GND resolves to In1.Cu only; power rails (+3V3/+5V/+15V) are *not* trace-routed
    as signals (handed to U4 pours).
  - `route_pcb()` with the JLC stackup restricts a `Signal`-class net's A* path to
    F.Cu/B.Cu cells only (assert no In1/In2 cells in the routed path).
  - Determinism: two runs produce identical assignments.
- **Verification:**
  `uv run pytest packages/temper-placer/tests/router_v6 -k "layer_assignment"`;
  manual `route_pcb` smoke asserts completion-rate unchanged vs W1 baseline.

---

### U3. IPC-2152 minimum-width calculator + integration

- **Goal:** Compute, per net, the **minimum** trace width required to carry its
  expected current under IPC-2152 with internal-layer derating for the net's
  assigned layer, and feed those widths into the existing trace-width assignment
  so no trace is under-sized.
- **Requirements:** R3
- **Dependencies:** U1 (copper weights/layer type), U2 (per-net layer).
- **Files:**
  - `packages/temper-placer/src/temper_placer/core/ipc2152.py` — **new.** Inverse
    ampacity: `min_width_mm(current_a, copper_oz, temp_rise_c, internal_layer) ->
    float`, plus `current_capacity(width_mm, ...)` forward for the gate (U6).
  - `packages/temper-placer/configs/net_currents.yaml` — **new.** Per-net expected
    currents from R3 (DC_BUS+ 16A, AC_L/AC_N 10A, +3V3/+5V 0.5A, +15V 0.2A,
    SW_NODE 16A, GATE_H/GATE_L 2A) with a documented default for unlisted nets.
  - `packages/temper-placer/src/temper_placer/router_v6/trace_width_assignment.py` —
    extend `_determine_trace_width` (line 82) to take the net's current + layer +
    copper weight and return `max(class_width, ipc2152_min_width)` with a `reason`
    naming the governing constraint.
  - `packages/temper-placer/src/temper_placer/router_v6/adapter.py` — thread the
    currents map + resolved layers into the width assignment call.
- **Approach:**
  - Implement IPC-2152 as the inverse of the ampacity curve rather than the
    IPC-2221 formula already in `core/ipc2221.py` (which is *forward* and more
    conservative). Provide the forward `current_capacity()` using the IPC-2152
    universal-chart fit (external base curve + internal-layer derating factor),
    then invert numerically (bisection over width, monotonic) to get
    `min_width_mm`. Document the fit source in the module docstring; keep the
    coefficients in one place.
  - Apply **internal-layer derating** using U2's assigned layer: F.Cu/B.Cu →
    external curve; In1.Cu/In2.Cu → internal curve (relevant for any plane-fed
    trace segment). Copper weight comes from U1 (`1oz` outer, `0.5oz` inner).
  - `_determine_trace_width` returns the **max** of the netclass `trace_width`
    (from `netclass_rules.yaml`) and the IPC-2152 minimum, so safety/clearance
    widths (ACMains 3.0mm) are never *reduced* and high-current widths are never
    *under*-sized. DC_BUS+/SW_NODE (16A) will demand a pour rather than a trace —
    the calculator flags `requires_pour=True` when the min width exceeds a routable
    threshold, handing those nets to U4.
  - Keep the existing `assign_trace_widths()` signature working (defaults) for
    callers that don't supply currents.
- **Patterns to follow:** `core/ipc2221.py` structure and unit conventions
  (mm↔mils, oz↔mils); `TraceWidth`/`TraceWidthAssignment` dataclasses
  (trace_width_assignment.py:16); YAML SSOT loader pattern.
- **Test scenarios:**
  - `min_width_mm(0.5, copper_oz=1.0, temp_rise=10, internal=False)` ≈ published
    IPC-2152 chart value within tolerance; monotonic in current.
  - 16A DC_BUS+ on 1oz F.Cu yields `requires_pour=True` (min width beyond routable
    threshold); 2A GATE_H yields a finite sub-mm width; 0.2A +15V ≥ netclass min.
  - Integration: every routed net's assigned width ≥ its IPC-2152 minimum for its
    layer/copper (this is the invariant U6 re-checks).
  - Round-trip: `current_capacity(min_width_mm(I)) ≈ I` (inverse consistency).
- **Verification:**
  `uv run pytest packages/temper-placer/tests -k "ipc2152"`; golden table compared
  against the R3 currents.

---

### U4. Power-domain pours, thermal via array, and via strategy

- **Goal:** Solid copper for each power domain on In2.Cu, a GND pour on In1.Cu, a
  DC_BUS+ thermal pour under Q1/Q2 on B.Cu fed by a via array, and a net-class via
  taxonomy — so no power pin is fed by a thin trace and Q1/Q2 heat has a path to
  the bottom-side pour.
- **Requirements:** R4, R5
- **Dependencies:** U1 (plane layers), U2 (which nets are pours vs traces), U3
  (`requires_pour` nets).
- **Files:**
  - `packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py` —
    extend `TEMPER_PLANE_NETS`/`TEMPER_PLANE_LAYERS` (lines 25–66) to emit a
    **per-domain pour** on In2.Cu for `+3V3`/`+5V`/`+15V` and a GND pour on In1.Cu;
    keep DC_BUS+/SW_NODE/AC_* on F.Cu pours as today, and add a DC_BUS+ pour on
    B.Cu under Q1/Q2.
  - `packages/temper-placer/src/temper_placer/router_v6/thermal_relief.py` — add a
    `thermal_via_array(component_ref, grid, drill, diameter)` that stamps a 2×2/3×3
    via grid under a component's collector pad, and call it for Q1/Q2 to stitch
    the F.Cu collector to the B.Cu DC_BUS+ pour. Reuse `add_thermal_relief`
    (line 85) for the pour-to-pad spokes.
  - `packages/temper-placer/src/temper_placer/router_v6/via_placement.py` /
    `via_grid_reservation.py` — add a via-class taxonomy: signal (0.6/0.3),
    power (1.0/0.5), thermal-array, stitching; select by net class from the SSOT.
  - `packages/temper-placer/configs/netclass_rules.yaml` — ensure each class's
    `via_diameter`/`via_drill` (already present) is the source for the taxonomy;
    add `via_role` (signal/power/thermal/stitch) where the class implies it.
- **Approach:**
  - **Pours:** reuse the existing `PowerPlaneStage` marking (it already routes
    power nets as plane connections, not traces). Split the single In2.Cu
    assignment into three domain pours keyed by net; each domain pour is a zone on
    In2.Cu isolated from the others and from signals by the core dielectric (R2).
    GND on In1.Cu is one continuous pour (the USB return reference for U5).
  - **Thermal:** Q1/Q2 are TO-247 IGBTs (IKW40N120H3). Place a via array under each
    collector pad (default 3×3, `via_role=thermal`, 1.0/0.5mm) connecting F.Cu
    collector → B.Cu DC_BUS+ pour. Reuse `_generate_spoke_segments`/`add_thermal_relief`
    for the pour-side thermal relief so soldering heat is managed while keeping
    low thermal resistance.
  - **Via taxonomy:** pull diameters/drills straight from `netclass_rules.yaml`
    (ACMains/HV/HighCurrent already 1.2/0.6; Signal 0.6/0.3; FinePitch 0.4/0.2).
    Stitching vias along plane edges use the GND class (1.0/0.5). Every via is
    tagged with a role for the gate/DRC.
  - No new pour geometry engine — extend the deterministic `power_plane` stage and
    `thermal_relief`, which already resolve `plane_layers` from
    `board.layer_stackup` (thermal_relief.py:137).
- **Patterns to follow:** `PowerPlaneStage` net→layer marking; `add_thermal_relief`
  plane-layer resolution and spoke generation; `_DEFAULT_PLANE_NETS`
  (thermal_relief.py:41) vs `TEMPER_PLANE_NETS` alignment.
- **Test scenarios:**
  - In2.Cu has 3 disjoint domain pours (+3V3/+5V/+15V); In1.Cu has one GND pour;
    each power net's pins connect to a pour (no thin-trace-only power pin — R4 gate).
  - A ≥2×2 thermal via array exists under **both** Q1 and Q2 (R5 gate) linking
    F.Cu collector to the B.Cu DC_BUS+ pour.
  - Via role/dimension selected per class matches `netclass_rules.yaml`; no via
    violates annular-ring DRC (reuse `annular_ring_check.py`).
  - Domain pours do not short (isolation gap ≥ class clearance).
- **Verification:**
  `uv run pytest packages/temper-placer/tests -k "power_plane or thermal_via"`;
  annular-ring check reports zero violations on the poured board.

---

### U5. USB differential pair — controlled impedance on F.Cu

- **Goal:** Route USB D+/D- as a length-matched, 90Ω-differential pair on F.Cu
  referenced to the In1.Cu GND plane, keeping ≥3mm from any HV/power trace on F.Cu.
- **Requirements:** R6
- **Dependencies:** U1 (0.2mm F.Cu↔In1.Cu prepreg + εr), U2 (USB on F.Cu, GND on
  In1.Cu), U4 (continuous In1.Cu GND reference).
- **Files:**
  - `packages/temper-placer/src/temper_placer/router_v6/differential_pair_constraints.py` —
    have `add_differential_pair_constraints` (line 43) read geometry (width 0.3mm,
    spacing 0.2mm) and reference layer from the stackup, and set
    `target_impedance=90` for USB (the `_infer_impedance` USB branch already
    returns 90.0, line 100).
  - `packages/temper-placer/src/temper_placer/core/` — add a small
    `diff_impedance.py` (edge-coupled microstrip) that computes differential
    impedance from U1's prepreg height/εr + width/spacing, used to *verify* the
    0.3/0.2 geometry lands 90Ω ±10% for this stackup.
  - `packages/temper-placer/src/temper_placer/router_v6/reference_plane_constraints.py` —
    ensure the USB pair's `required_plane` resolves to the In1.Cu GND plane
    (add_reference_plane_constraints already emits GND for `_P`/`_N`/USB nets,
    lines 126–131); make it read the actual adjacent plane from
    `StackupInfo.get_reference_plane`.
  - `packages/temper-placer/src/temper_placer/router_v6/length_matching.py` — wire
    the pair's `max_length_mismatch=0.5mm` (already the diff-pair default) into the
    length-matching pass for the USB pair.
- **Approach:**
  - `infer_differential_pairs()` (diff_pair_inference.py:37) already detects
    `USB_D+`/`USB_D-`. Feed those into the constraint builder with
    width=0.3/space=0.2/impedance=90/skew≤0.5 sourced from R6, and pin the pair to
    F.Cu with In1.Cu reference (from U1/U2).
  - Use `diff_impedance.py` to assert the geometry meets 90Ω ±10% for the *actual*
    0.2mm prepreg / εr≈4.2 — this is the design-time check that mirrors the Saturn
    PCB Toolkit value called out in R6; it also feeds U6's measurement.
  - **HV separation:** add a ≥3mm keep-away between the USB pair and any
    ACMains/HighVoltage/HighCurrent trace on F.Cu, expressed through the existing
    `class_pairs` clearance mechanism (netclass_rules.yaml `class_pairs`, line 82)
    — add a `USB`-vs-HV pair entry rather than new geometry code.
  - Length matching keeps the pair skew ≤0.5mm via the existing serpentine/length
    passes (`serpentine.py`, `length_matching.py`).
- **Patterns to follow:** `DifferentialPairConstraint` dataclass and
  `_infer_impedance` (differential_pair_constraints.py); `class_pairs` clearance
  SSOT; `add_reference_plane_constraints` GND resolution.
- **Test scenarios:**
  - USB pair detected and constrained: impedance target 90Ω, width 0.3, space 0.2,
    reference In1.Cu, layer F.Cu.
  - `diff_impedance` on (0.3, 0.2, 0.2mm prepreg, εr 4.2) returns 90Ω ±10%.
  - Routed pair length skew ≤ 0.5mm.
  - Any HV/power F.Cu trace is ≥3mm from the USB pair (clearance pair honoured).
  - USB pair never leaves F.Cu / never loses the In1.Cu GND reference (no plane
    split under the pair).
- **Verification:**
  `uv run pytest packages/temper-placer/tests -k "diff_pair or usb or impedance"`.

---

### U6. `StackupGate` — reference-plane split + IPC-2152 current density

- **Goal:** A routing-stage `Gate` (per the gate contract) that inspects the routed
  `BoardState` and returns `CLEAN`/`VIOLATIONS`/`UNMEASURED`: `VIOLATIONS` when a
  signal net crosses a reference-plane split or any trace is below its IPC-2152
  minimum current density; `UNMEASURED` (fail-closed) when the stackup, zones, or
  routed geometry cannot be read.
- **Requirements:** R2, R3 gates (and the contract itself).
- **Dependencies:** U2 (layer assignments), U3 (IPC-2152), U4 (pours/planes),
  U5 (diff-pair reference).
- **Files:**
  - `packages/temper-placer/src/temper_placer/router_v6/gates/stackup_gate.py` —
    **new.** `StackupGate` with `stage = GateStage.ROUTING`, `name = "stackup"`,
    `check(state) -> GateResult`, `to_delta(v) -> ConstraintDelta | None`.
  - `packages/temper-placer/src/temper_placer/router_v6/gates/__init__.py` — **new**
    (or extend if W1 created it) re-exporting the shared contract types.
  - **Shared contract types:** import `Gate`, `GateResult`, `GateStatus`,
    `GateStage`, `Violation`, `ViolationType`, `BoardState`, `ConstraintDelta` from
    the W1/W5-owned module (expected `temper_placer.gates.contract`). **If that
    module does not exist yet** (W1/W5 not landed), create a minimal
    `temper_placer/gates/contract.py` shim exactly matching the contract dataclasses
    and mark it `# TODO(W5): consolidate` so the registry can absorb it.
- **Approach:**
  - **Reference-plane split (R2 gate):** for each routed signal net, walk its
    segments; using U1's `get_reference_plane`, confirm the layer directly below
    each F.Cu/B.Cu segment is a *continuous* plane pour (from U4) with no zone gap
    beneath the trace. A crossing yields a `Violation(type=REFERENCE_PLANE_SPLIT,
    …)`. Reuse `reference_plane_constraints` to know each net's required plane.
  - **Current density (R3 gate):** for each routed net, compare its assigned width
    (U3) against `min_width_mm(current, copper_oz(layer), temp_rise, internal)`;
    width below minimum → `Violation(type=CURRENT_DENSITY, severity=actual_width,
    threshold=min_width, …)`.
  - **Fail-closed:** wrap measurement in `try/except`; a missing stackup, empty
    zones, unreadable `routed_pcb_path`, or a calculator exception returns
    `GateResult(UNMEASURED, error_message=…)` — never `CLEAN`. Mirrors the
    `PhysicsGate` example in the contract (gate-contract.md:130) and the
    `run_drc` false-zero lesson (line 47).
  - **ViolationType extension:** the contract enum
    (`CLEARANCE, UNROUTED, LOOP_INDUCTANCE, THERMAL, CREEPAGE, VIA_COUNT, SLOP`)
    has no stackup member. **Decision to coordinate with W5:** add
    `REFERENCE_PLANE_SPLIT` and `CURRENT_DENSITY` to the shared `ViolationType`.
    Interim (before W5 owns the enum) map plane-split→`CLEARANCE` and current
    -density→`THERMAL` and leave a `# TODO(W5)` — but prefer the explicit members.
  - **`to_delta`:** current-density → a width-increase delta (`min_width` for the
    net); plane-split → typically `None` (routing must re-path, not a placement
    delta), matching the contract's "returns None when no corrective delta" clause.
- **Patterns to follow:** the `PhysicsGate`/`DrcGate` examples in the gate contract
  (three-state discipline, `try/except → UNMEASURED`, `to_delta` mapping);
  `validation/validation_gates.py` existing gate style for local conventions.
- **Test scenarios:**
  - Clean routed board (all U1–U5 satisfied) → `GateStatus.CLEAN`, zero violations.
  - A signal net deliberately routed over an In2.Cu domain gap → one
    `REFERENCE_PLANE_SPLIT` violation with the offending net/segment in `context`.
  - A 16A net narrowed below its IPC-2152 minimum → one `CURRENT_DENSITY` violation
    with `severity`/`threshold` set; `to_delta` proposes the min width.
  - Stackup/zones missing or `routed_pcb_path=None` → `UNMEASURED` with a non-empty
    `error_message`; **never** `CLEAN`.
  - `to_delta` returns `None` for plane-split, a width delta for current-density.
- **Verification:**
  `uv run pytest packages/temper-placer/tests/router_v6/gates -k "stackup_gate"`;
  assert `all_gates_green` treats an `UNMEASURED` StackupGate as blocking.

---

## Gate Contract Conformance (cross-cutting)

`StackupGate` (U6) is the W2 obligation under
`docs/brainstorms/2026-07-08-gate-contract.md`:

- **Stage:** `ROUTING` (checked after routing completes, alongside RoutingGate /
  PhysicsGate / QualityGate).
- **Three-state:** `CLEAN` (measured, zero violations), `VIOLATIONS` (measured,
  plane-split or current-density found → emit `to_delta`), `UNMEASURED` (could not
  measure → blocks convergence). Never returns `[]` to mean "clean" on a
  measurement failure.
- **Registry:** W5 owns `PlaceRouteLoop.gates` and `all_gates_green`; W2 only
  supplies the gate object and (with W5) the two new `ViolationType` members. No
  loop orchestration is implemented here.

---

## Sequencing & Risks

**Order:** U1 → U2 → U3 → U4 → U5 → U6. U1 is the physical foundation; U2 depends
on U1's layer model; U3 needs U1 copper + U2 layer; U4 needs U2's pour/trace split
and U3's `requires_pour`; U5 needs U1 prepreg + U2/U4 GND plane; U6 measures the
outputs of U2–U5.

**Risks / decisions to confirm before coding:**
1. **Copper-weight change** (2oz→1oz outer). `default_4layer()` stays as-is;
   the JLC stackup is a *new* classmethod so nothing that assumes 2oz F.Cu
   silently changes. Confirm no consumer hard-depends on 2oz F.Cu ampacity.
2. **Layer numbering unification** (KiCad names as SSOT vs the `Layer` L1..L4
   enum). Single mapping helper in U2; align with `2026-06-23-008` consolidation.
3. **IPC-2152 vs the existing IPC-2221 module.** New `core/ipc2152.py` (inverse +
   internal derating); do **not** repurpose `ipc2221.py` (forward, conservative).
   Document the chart-fit source.
4. **`ViolationType` extension** must be coordinated with the W5 registry owner
   (shared enum). Interim mapping documented in U6.
5. **Gate contract types not yet in code.** W1/W5 are expected to land
   `temper_placer.gates.contract`; U6 ships a matching shim if they haven't, with
   a `TODO(W5)` to consolidate — avoids blocking W2 on W5.

---

## Success Criteria (traceable to requirements)

1. **R1** — `LayerStackup.jlc04161h_7628()` + `stackup_jlc04161h_7628.yaml` match
   the JLCPCB offering (1oz/0.5oz, 0.2/1.1/0.2mm, 1.6mm total); loader tests green.
2. **R2** — all 9 net classes carry a deterministic `layer` in
   `netclass_rules.yaml`; `route_pcb()` restricts signals to F.Cu/B.Cu; no signal
   allowed on In2.Cu.
3. **R3** — `core/ipc2152.py` sizes every net ≥ its current-density minimum;
   integrated into `trace_width_assignment`; golden table matches R3 currents.
4. **R4/R5** — In1.Cu GND pour + 3 In2.Cu domain pours; ≥2×2 thermal via array
   under Q1 and Q2 to the B.Cu DC_BUS+ pour; via taxonomy from the SSOT; zero
   annular-ring violations.
5. **R6** — USB D+/D- routed on F.Cu, In1.Cu reference, 90Ω ±10%, skew ≤ 0.5mm,
   ≥3mm from HV/power on F.Cu.
6. **Contract** — `StackupGate` returns `CLEAN`/`VIOLATIONS`/`UNMEASURED`
   correctly, fails closed, and is consumable by the W5 registry.

## Global Verification

```bash
uv run pytest packages/temper-placer/tests -k \
  "stackup or layer_assignment or ipc2152 or power_plane or thermal_via or diff_pair or impedance or stackup_gate"
uv run python scripts/import_linter_gate.py      # boundary check (AGENTS.md)
```
