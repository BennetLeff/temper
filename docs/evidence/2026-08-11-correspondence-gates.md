<!-- provenance: commit=528afb18b0c0e4fc09ff6980298ef9d4d06ba474 dirty=false (base) -->

# Correspondence gates: three classes of silent drift, made impossible to recur

Three real defects were found on 2026-08-11, each undetected for
days-to-weeks: a broken PCL placement config (PR #1026), never-poured
power planes (post `c4956df66`), and drifted `kicad_pro` netclass
assignments that silently disabled DRC checks (PR #1023). They share one
shape: **an artifact declares something, and nothing verifies that the
rest of the system honours the declaration.**

This document adds three `scripts/check_*.py` CI gates, one per defect
class, plus a fourth that generalises the third to every other
hand-maintained copy of the same SSOT found by survey. Per gate, up
front: the command, the failing run, and what "fixed" would look like.

| Gate | Script | Real-repo state today | CI status |
|---|---|---|---|
| 1. Config <-> board correspondence | `scripts/check_pcl_config_board_correspondence.py` | **VIOLATION** (exit 3) -- 24 broken component references, 3 zones outside the board outline | Advisory (`continue-on-error: true`) |
| 2. Declared <-> emitted layers | `scripts/check_layer_plane_emission_coverage.py` | **VIOLATION** (exit 3) -- parser discards the role token, `In1.Cu`/`In2.Cu` have no emitter path | Advisory (`continue-on-error: true`) |
| 3. Net-class map <-> board correspondence | `scripts/check_netclass_map_board_correspondence.py` | **VIOLATION** (exit 3) -- 31 broken keys across 4 hand-maintained files | Advisory (`continue-on-error: true`) |

All three gates are wired into `.github/workflows/python-tests.yml`'s
`consistency-gates` job (`Cross-Source Consistency Gates`), each with its
own pytest unit-test step ahead of it. `.github/required-checks.json` was
extended so a change to any of the gates' own real inputs (the PCL
config, the alias manifest, `parse_engine.rs`, `_zone_pour_stitch.py`,
`configs/**`, `packages/temper-placer/configs/**`) triggers that job on a
PR, not only a change under `scripts/**` (which the pre-existing
`catch_all_paths` entry already covered).

All three currently violate on `origin/main` -- see "Advisory vs.
blocking" per gate below for why each is landed advisory rather than
hard-failing, and the named, concrete change that flips it.

---

## Gate 1: PCL config <-> board correspondence

**Script:** `scripts/check_pcl_config_board_correspondence.py`
**Tests:** `scripts/tests/test_check_pcl_config_board_correspondence.py` (22 tests)

### The defect (PR #1026 and its triage table)

`packages/temper-placer/configs/constraints/temper_induction_cooker.yaml`
holds 21 placement constraints against `pcb/temper.kicad_pcb` (169
components, 152x234mm). Not one has a safe mechanical fix:

- `J_AC_IN`, `J_COIL`, `J_DEBUG` name components that do not exist on the
  board at all.
- `adj_Q1_Q2` (`adjacent: {a: Q1, b: Q2}`) resolves to unrelated small
  transistors. `Q1`/`Q2` **are** real board Reference designators
  (`pcb/temper.kicad_pcb` has footprints literally named `Q1`/`Q2`), so a
  naive "does this name exist on the board" check would pass this
  constraint. The board's own hand-reconciled alias manifest,
  `packages/temper-placer/configs/temper_constraints.references.yaml`,
  documents the real intent was the IGBTs (board refs `U5`/`U6`,
  measured ~91.5mm apart against the constraint's `max_distance_mm: 10`).
- The zone geometry (`MCU_ZONE`/`ISOLATION_BARRIER`/`HV_ZONE`, origin
  `(0,0)`, sized for a 100x150mm board) is not merely undersized against
  the real 152x234mm board -- its bounding box `[0,0,100,150]` starts
  20mm outside the real board outline's own origin corner. Parsed
  directly from `pcb/temper.kicad_pcb`'s `gr_poly` Edge.Cuts geometry,
  the real outline is `(20,20)-(172,254)`.

Nothing before this gate checked that the config's component references
resolve, or that its zones fit the board -- PR #1026 fixed the *loader*
(it no longer silently swallows a load error), not the config's content.

### Design

Two independent properties, because fixing one does not imply the other
is fixed:

1. **Component reference resolution.** Every component-context name
   (`adjacent.a`/`.b`, `separated.a`/`.b`, `on_side.components`,
   `aligned.components`, `enclosing.inner`) must resolve to a real board
   Reference. Resolution order is deliberately **manifest-first**:
   `unresolved_components` (the alias manifest's list of known-broken
   names) is checked *before* a literal board-reference match -- this is
   what correctly flags `Q1`/`Q2` as broken even though both are real
   designators for the wrong part. A name that instead appears in
   `component_aliases` resolves through it; anything left over that
   matches nothing (no zone, no alias, no unresolved entry, no direct
   board match) is also broken, fail-closed.
2. **Zone containment.** Every zone's `[x_min, y_min, x_max, y_max]`
   bounds must be fully contained in the board's own Edge.Cuts bounding
   box, computed directly from the board file (never a hardcoded
   board-size constant), so this property tracks the board through any
   future resize.

Constraint types outside a known field-extraction table make the gate
fail closed (exit 5) rather than silently skip -- an unrecognized
constraint type is a gate blind spot, not a clean pass. This gate parses
**zero** component coordinates and computes **zero** distances: it is
strictly a config-well-formedness check, never a placement-quality
check. A constraint the board's *actual placement* merely violates is
explicitly out of scope, and always will be.

### Proof: fails on the real defect

```
$ uv run python scripts/check_pcl_config_board_correspondence.py
PCL config <-> board correspondence gate -- 20 constraint(s) and 3 zone(s) checked

=== PROPERTY 1: BROKEN COMPONENT REFERENCES: 24 ===
  VIOLATION constraint[3] (type='adjacent') references 'Q1': live designator is power_in.q_relay_drv; legacy config means hb.power_loop.q_high (board ref U5)
  VIOLATION constraint[3] (type='adjacent') references 'Q2': live designator is discharge.q_dis_drv; legacy config means hb.power_loop.q_low (board ref U6)
  ...
  VIOLATION constraint[8] (type='separated') references 'J_AC_IN': no source-backed connector instance
  VIOLATION constraint[15] (type='on_side') references 'J_COIL': no source-backed connector instance
  VIOLATION constraint[17] (type='on_side') references 'J_DEBUG': no source-backed connector instance
  ... (24 total, spanning constraint[3..19])

=== PROPERTY 2: ZONES OUTSIDE BOARD OUTLINE: 3 ===
  VIOLATION zone 'MCU_ZONE': bounds [0.0, 0.0, 100.0, 70.0] is not contained in the board outline [20.0, 20.0, 172.0, 254.0] (from pcb/temper.kicad_pcb's own Edge.Cuts geometry)
  VIOLATION zone 'ISOLATION_BARRIER': bounds [0.0, 70.0, 100.0, 80.0] is not contained in the board outline [20.0, 20.0, 172.0, 254.0] (from pcb/temper.kicad_pcb's own Edge.Cuts geometry)
  VIOLATION zone 'HV_ZONE': bounds [0.0, 80.0, 100.0, 150.0] is not contained in the board outline [20.0, 20.0, 172.0, 254.0] (from pcb/temper.kicad_pcb's own Edge.Cuts geometry)

FAILED -- 24 broken reference(s), 3 zone(s) outside the board outline
$ echo $?
3
```

Every one of the three named defect instances (`J_AC_IN`, `J_COIL`,
`J_DEBUG`, `adj_Q1_Q2`, oversized/mislocated zones) is present in this
output. No git-history reconstruction was needed for the "before" side:
this **is** the current state of `origin/main` -- the config has never
been fixed, only the loader that reads it (#1026).

### Proof: the check is sound (passes when the inputs are correct)

Since `origin/main`'s real config has no "after" state to point at yet,
soundness is proven with synthetic fixtures
(`test_check_pcl_config_board_correspondence.py::TestMutations`):

- `test_alias_resolves_to_real_board_ref_is_clean` -- a config using
  `U_GATE`/`C_BUS1` (which resolve via `component_aliases` to real board
  refs `U7`/`C2`) is clean.
- `test_zone_within_board_outline_is_clean` -- a zone whose bounds sit
  inside the board outline is clean.
- `test_unresolved_components_flagged_even_when_name_matches_a_real_ref`
  -- reproduces the exact `adj_Q1_Q2` shape synthetically (a board with
  literal `Q1`/`Q2` footprints, a manifest that lists both as
  `unresolved_components`) and confirms the gate flags them, proving the
  manifest-first resolution order actually fires rather than being
  shadowed by the direct-match branch.
- `test_fixing_only_one_property_leaves_the_other_violation` -- confirms
  the two properties are independent (this repo's `check_hv_netclass_coverage.py`
  precedent).

All 22 tests pass, including `TestAntiVacuity` (9 tests covering every
degenerate input: missing/empty config, missing/malformed board,
zero-footprint board, no-Edge.Cuts board, missing/malformed reference
manifest, unknown constraint type) and `TestRealRepoIntegration` (pins
the exact current-`main` violation set, so a future config fix is
required to touch this test too, not just silently go green).

### Advisory vs. blocking

**Advisory.** The task brief itself states the config's brokenness has
no safe mechanical fix in this session (deciding which real IGBT pair
Q1/Q2 constraints should target, or whether the J_AC_IN/J_COIL/J_DEBUG
connectors should be added to the board or the constraints deleted, is a
board-completeness/design decision, not a rename). Landing this gate
hard-failing today would block every unrelated PR touching the PCL
config or the board.

**Path to blocking:** fix `temper_induction_cooker.yaml` --
drop or re-target the `J_AC_IN`/`J_COIL`/`J_DEBUG`/`Q1`/`Q2` constraints
(the file already has a working precedent for this: five other
config↔netlist-drift constraints are commented out with a `DISABLED
(config<->netlist drift)` note and a named reason -- see `C_VCC1`/
`C_VCC2`, `D_BOOT`/`C_BOOT`, `J_FAN`, `C_TANK`, `CT1` in the file today),
and resize the three zones to the real 152x234mm board. Confirm
`uv run python scripts/check_pcl_config_board_correspondence.py` exits 0,
then remove `continue-on-error: true` from the workflow step.

---

## Gate 2: Declared <-> emitted layers

**Script:** `scripts/check_layer_plane_emission_coverage.py`
**Tests:** `scripts/tests/test_check_layer_plane_emission_coverage.py` (18 tests)

### The defect (`c4956df66` and the same-day follow-up investigation)

`c4956df66` ("declare In1.Cu/In2.Cu as power-plane layers, not signal")
correctly changed `pcb/temper.kicad_pcb`'s layer-stack declaration:

```
(1 "In1.Cu" signal) -> (1 "In1.Cu" power)
(2 "In2.Cu" signal) -> (2 "In2.Cu" power)
```

Both layers are still empty on the real board -- zero copper of any
kind -- for two independent reasons, both confirmed still live on
`origin/main`:

1. `packages/temper-design-bundle/src/parse_engine.rs`'s
   `raw_board_from_tree` reads only the quoted NAME token (index 1) of
   each `(N "LayerName" role)` entry and never touches index 2 -- the
   code's own comment says "index 2 is the layer type" immediately
   before discarding it.
2. `packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py`'s
   `_zone_layers_for_net` -- the function `_adapter_convert.route_pcb`
   (the actual production routing entry point) uses to choose zone
   layers -- can only ever return `["F.Cu", "B.Cu"]` or `[]`. No return
   path anywhere reachable from `route_pcb` can produce `"In1.Cu"` or
   `"In2.Cu"`.

`router_v6/power_plane.py` **does** contain layer-aware plane-pour
geometry generation (`generate_ground_pour` on `In1.Cu`,
`generate_power_pours` on `In2.Cu`) -- but tracing its only call site
(`_pipeline_verify.py`'s `_run_manufacturing_drc`) shows it is invoked
purely to log a `"Power planes: ..."` summary line for the manufacturing
report; the geometry it computes is never merged into `route_pcb`'s
`routed_pcb_content`. A code path that computes plane geometry nobody
writes to the board is not an emitter for this gate's purposes --
Property 2 below is deliberately scoped to the one function that is
actually wired into the pipeline that produces the board, not to every
function in the codebase that happens to know how to draw a plane.

Meanwhile `scripts/route_board.py`'s `_should_route()` excludes
power/ground/HV nets from point-to-point routing entirely (12 of 110
nets, "presumed zone-covered"). Net `gnd` -- 86 pads, the board's
largest -- ends up with zero copper of any kind: no pour (this defect),
no point-to-point routing (excluded on the promise of a pour).

### Design

Two independent properties:

1. **Parser role-token fidelity** -- a static source-text check
   (deterministic, no compile) scoped precisely to `raw_board_from_tree`'s
   own `"layers" => { ... }` match arm (there are two *other*, unrelated
   `"layers" =>` arms in the same file, for pad/zone layer lists, which
   have no per-entry role token at all -- the gate locates
   `raw_board_from_tree`'s function boundary first, then searches only
   within it, so it cannot be fooled by either decoy).
2. **Zone-emitter layer coverage** -- every layer
   `pcb/temper.kicad_pcb`'s own `(layers ...)` block declares with role
   `"power"` must appear as a string literal inside `_zone_layers_for_net`'s
   body (extracted by locating the function and reading up to the next
   top-level `def`).

### Proof: fails on the real defect

```
$ uv run python scripts/check_layer_plane_emission_coverage.py
Declared <-> emitted layer gate -- 2 declared power-plane layer(s): ['In1.Cu', 'In2.Cu']

=== PROPERTY 1: PARSER ROLE-TOKEN FIDELITY ===
  VIOLATION raw_board_from_tree's 'layers' arm in .../parse_engine.rs only reads index 1 (the name) -- the role/type token at index 2 of each `(N "Name" role)` entry is discarded, so nothing downstream of parsing can learn a layer's declared power-plane role

=== PROPERTY 2: PLANE LAYERS WITH NO EMITTER PATH: 2 ===
  VIOLATION layer 'In1.Cu' is declared with role 'power' in pcb/temper.kicad_pcb but does not appear anywhere in _zone_layers_for_net's body -- no code path reachable from route_pcb can ever pour copper on it
  VIOLATION layer 'In2.Cu' is declared with role 'power' in pcb/temper.kicad_pcb but does not appear anywhere in _zone_layers_for_net's body -- no code path reachable from route_pcb can ever pour copper on it

FAILED -- parser role-token fidelity: VIOLATION, 2 plane layer(s) with no emitter path
$ echo $?
3
```

### Proof: reconstructed pre-fix state (anti-vacuity, not a false "clean")

`c4956df66`'s parent commit declared all copper layers `signal` -- i.e.
zero declared plane layers existed yet. Running the gate against that
reconstructed board confirms it correctly refuses to report a vacuous
"clean" (there being nothing to check is not evidence of correctness):

```
$ git show c4956df66~1:pcb/temper.kicad_pcb > /tmp/board_pre_c4956df66.kicad_pcb
$ uv run python scripts/check_layer_plane_emission_coverage.py --board /tmp/board_pre_c4956df66.kicad_pcb
GATE RESULT: ERROR -- not PASSED, not a violation. The gate could not run a trustworthy check.
Declared <-> emitted layer gate -- 0 declared power-plane layer(s): []

1 TOOL ERROR(S)
  TOOL_ERROR /tmp/board_pre_c4956df66.kicad_pcb declares zero layers with role 'power' -- vacuous run, not a clean pass
$ echo $?
5
```

This traces the gate's verdict through the real history: pre-`c4956df66`
GATE ERROR (nothing declared yet, correctly refuses to pass vacuously) ->
current `main` VIOLATION (declared, but unreachable) -> (hypothetical,
both bugs fixed) PASSED. The middle and end states are also proven with
synthetic mutations, since the real "both fixed" state doesn't exist yet:

- `check_parser_captures_layer_role` against a scratch copy of the real
  arm text with `s.get(2)` added returns `True`
  (`TestParserRoleTokenFidelity::test_fixed_arm_passes`).
- `load_emittable_layers`/`check_emitter_covers_declared_planes` against
  a scratch copy of `_zone_layers_for_net` with `"In1.Cu", "In2.Cu"`
  added to its return list finds zero missing layers
  (`TestZoneEmitterCoverage::test_fixed_emitter_covers_declared_planes`).
- `TestRunEndToEnd::test_both_fixed` combines both into a full `run()`
  call and confirms `state == "clean"`.

All 18 tests pass.

### Advisory vs. blocking

**Advisory.** Both underlying bugs require real engineering, not a
config edit: the parser fix touches a `pyo3`/`maturin` Rust crate's
public `RawBoard` struct, and the emitter fix means either giving
`_zone_layers_for_net` a real per-net-class-to-declared-plane-layer
resolution, or wiring `power_plane.py`'s already-correct geometry into
`route_pcb`'s emitted content instead of only `_pipeline_verify.py`'s
report. Landing this gate hard-failing today would block every PR that
merely touches `parse_engine.rs`, `_zone_pour_stitch.py`, or the board,
for a pre-existing defect this PR does not fix.

**Path to blocking:** (1) capture the role token in
`raw_board_from_tree` (`parse_engine.rs`) -- a small, additive,
low-risk change (read `s.get(2)` alongside `s.get(1)`); (2) give
`_zone_layers_for_net` a real layer resolution reaching `In1.Cu`/`In2.Cu`
for plane-classed nets, wired all the way through to
`routed_pcb_content`. Confirm the gate exits 0 against the regenerated
board, then remove `continue-on-error: true`.

---

## Gate 3 (+ generalisation): net-class map <-> board correspondence

**Script:** `scripts/check_netclass_map_board_correspondence.py`
**Tests:** `scripts/tests/test_check_netclass_map_board_correspondence.py` (14 tests)

### Scope note: this does not duplicate #1023 / #1025

Defect 3's proximate cause was `pcb/temper.kicad_pro`'s
`net_settings.classes[].netclass_assignments` drifting from
`TEMPER_NET_ASSIGNMENTS`. PR #1023 fixed that specific pair; PR #1025 is
landing a generator with `--check` mode for exactly that pair. This gate
does not touch `pcb/temper.kicad_pro` and does not re-implement that
generator.

### The survey (this task's explicit ask: find other copies of the same SSOT)

A background survey searched the repo for other hand-maintained copies
of "which net belongs to which class" -- the same failure shape as
defect 3, in a different pair of files. It found four, independently of
the `kicad_pro`/`TEMPER_NET_ASSIGNMENTS` pair, all verified directly
against `pcb/temper.kicad_pcb`'s own net table:

| File | Consumer | Broken keys (of total) |
|---|---|---|
| `configs/temper_deterministic_config.yaml` | `scripts/run_feedback_loop.py` -> `Netlist.apply_net_class_mapping` | 21 of 25 (`AC_L`, `AC_N`, `DC_BUS+`, `DC_BUS-`, `GND`, `PGND`, `CGND`, `VCC_BOOT`, `GATE_H`, `GATE_L`, ...) |
| `configs/temper_production_config.yaml` | (comment: "not loaded by any code path today") | 1 of 29 (`+340V_BUS`) |
| `packages/temper-placer/configs/temper_constraints.yaml` | loaded via `load_constraints` in `cli/__init__.py` | 4 of 11 (`+340V_BUS`, `AC_L`, `AC_N`, `PE`, `GND`) |
| `packages/temper-placer/configs/gate_driver_constraints.yaml` | (same family) | 4 of 5 (`GATE_H`, `GATE_L`, `CGND`, `VCC_BOOT`) |

`Netlist.apply_net_class_mapping`'s own docstring states the failure
mechanism directly: *"Nets not in the mapping retain their current
net_class (typically the default 'Signal')"* -- exact-key dict lookup,
silent no-op on a miss, no warning, no error, not even a count mismatch
surfaced anywhere. This is the same shape as `TEMPER_NET_ASSIGNMENTS`'
fallthrough that motivated `check_hv_netclass_coverage.py`: a
mains-voltage net (`AC_L`/`AC_N`, real names `ac_l`/`ac_n`; `+340V_BUS`,
renamed to `+170V_BUS` per `elec/domain_manifest.yaml`'s own comment)
silently inherits the lowest-clearance default class because the
`net_classes:` key that was supposed to classify it never matched
anything.

Two other candidates were surveyed and are deliberately **not** gated
here (documented, not built, to keep this unit's scope to what was
asked):

- `generate_kicad_dru.py`'s hand-written `class_order` list omits
  `HighVoltageIsolated` (present in `TEMPER_NET_CLASSES`), so that
  class's trace-width DRU rule specifically is never emitted (its
  clearance rule, checked by `check_hv_netclass_coverage.py`'s Property
  2, is emitted through a different code path and does exist -- this is
  a narrower, still-real gap that gate does not see). This needs a real
  fix (drive the emission loop from `TEMPER_NET_CLASSES` directly, or
  assert `set(class_order) == set(TEMPER_NET_CLASSES)`), not just a
  gate, and touches DRU generation this task's boundaries did not ask
  for.
- Board-dimension constants (`100x150mm`) are hand-copied into
  `configs/temper_deterministic_config.yaml`, `configs/temper_production_config.yaml`,
  and `_constraint_types/config.py`, all still 100x150 against the real
  152x234mm board. This is the same *shape* as Gate 1's zone-containment
  property, on different files -- a natural follow-on for the same
  gate's pattern rather than a new one.

### Design

Discovery, not a hand-maintained file list (itself the same
duplication risk): every top-level `*.yaml` directly under `configs/`
and `packages/temper-placer/configs/` (non-recursive, matching where all
four instances live) is parsed; any file whose top-level `net_classes`
key is a `{str: str}` mapping is a candidate (a nested, differently
shaped `net_classes: ["ACMains"]` per-rule field that appears inside
some of these same files is explicitly not a false positive -- tested).
Every key of every candidate is checked against the real net names
parsed directly from `pcb/temper.kicad_pcb`'s own net table. The
invariant is unconditional: a `net_classes:` key that is not a real net
name can never affect anything, on any consumer, ever -- unlike a
component reference, a net name is fixed by the compiled design, not a
placement decision, so there is no legitimate "not yet placed" escape
hatch here.

### Proof: fails on the real defect

```
$ uv run python scripts/check_netclass_map_board_correspondence.py
Net-class map <-> board correspondence gate -- 4 file(s), 70 key(s) checked
  scanned: configs/temper_deterministic_config.yaml
  scanned: configs/temper_production_config.yaml
  scanned: packages/temper-placer/configs/gate_driver_constraints.yaml
  scanned: packages/temper-placer/configs/temper_constraints.yaml

=== BROKEN net_classes KEYS: 31 ===
  VIOLATION configs/temper_deterministic_config.yaml: net_classes['AC_L'] = 'HighVoltage' -- 'AC_L' is not a real net name on the board; this assignment is a silent no-op
  VIOLATION configs/temper_deterministic_config.yaml: net_classes['DC_BUS+'] = 'HighVoltage' -- ...
  VIOLATION configs/temper_deterministic_config.yaml: net_classes['GATE_H'] = 'Signal' -- ...
  ... (21 total in this file)
  VIOLATION configs/temper_production_config.yaml: net_classes['+340V_BUS'] = 'HighVoltage' -- ...
  VIOLATION packages/temper-placer/configs/gate_driver_constraints.yaml: net_classes['GATE_H'] = 'GateDrive' -- ...
  VIOLATION packages/temper-placer/configs/gate_driver_constraints.yaml: net_classes['CGND'] = 'GND' -- ...
  VIOLATION packages/temper-placer/configs/gate_driver_constraints.yaml: net_classes['VCC_BOOT'] = 'Power' -- ...
  ... (4 total in this file)
  VIOLATION packages/temper-placer/configs/temper_constraints.yaml: net_classes['+340V_BUS'] = 'HighVoltage' -- ...
  VIOLATION packages/temper-placer/configs/temper_constraints.yaml: net_classes['AC_L'] = 'ACMains' -- ...
  ... (4 total in this file)

FAILED -- 31 broken net_classes key(s)
$ echo $?
3
```

### Proof: the check is sound (passes when the inputs are correct)

`test_matching_keys_are_clean` builds a synthetic board + config where
every key (`ac_l`, `ac_n`, `GATE_HS`) is real, and confirms `state ==
"clean"`. `test_stale_key_is_broken` and `test_case_mismatch_key_is_broken`
reproduce the `+340V_BUS` and `AC_L`/`ac_l` shapes synthetically and
independently of the real repo state. `test_nested_list_shaped_net_classes_key_is_not_a_false_positive`
proves the discovery step does not trip on the unrelated nested
`net_classes: ["ACMains"]` shape that coexists in some of the same real
files. All 14 tests pass, including anti-vacuity (5 tests: missing
board, no-net board, zero candidate files, malformed YAML candidate) and
`TestRealRepoIntegration` (pins the exact current 4-file, 31-key
violation set).

### Advisory vs. blocking

**Advisory.** Some of the 31 broken keys are safe, mechanical renames
(`+340V_BUS` -> `+170V_BUS` per `elec/domain_manifest.yaml`'s own rename
comment; `AC_L`/`AC_N` -> `ac_l`/`ac_n`, an exact case-fold). Others are
not: `gate_driver_constraints.yaml`'s `CGND`/`VCC_BOOT` match no net on
the current board in any form (case-folded or otherwise) and need the
same kind of human/domain reconciliation
`temper_constraints.references.yaml` required for Gate 1's component
references, not a rename. Landing this gate hard-failing today, across
four files with two different repair difficulties, in a PR whose job is
building the gate rather than making that reconciliation call, would
either block unrelated work or force a rushed guess at the harder half.

**Path to blocking:** reconcile all 31 keys against the real board net
table (the obvious renames first; the `CGND`/`VCC_BOOT`-shaped ones need
a documented decision, mirroring `temper_constraints.references.yaml`'s
`unresolved_components` treatment for Gate 1). Confirm the gate exits 0,
then remove `continue-on-error: true`.

---

## The general pattern, and a concrete rule for future declarations

**Pattern:** a declaration in artifact A (a config file, a board file, a
generated project file) is trusted by system S (a placer, a router, a
DRC engine) without S, or anything else, ever checking that A's
declaration is *realizable* against S's actual inputs. The three defects
this document addresses are the same shape at three different layers:
A = a placement constraint / a board layer stack / a netclass-assignment
table; S = the CP-SAT placer / the zone-pour emitter / KiCad's DRC
engine.

**Concrete rule:** whenever a change introduces (a) a new file that
declares facts about named entities from another artifact (component
refs, net names, layer names, class names, ...), or (b) a new hand-
written mapping whose keys are supposed to match names defined
elsewhere, that PR must also add or extend a correspondence check
satisfying three properties, in the same idiom as the three gates above:

1. **Ground truth is read directly from the authoritative artifact**,
   never a second hardcoded copy of it (Gate 1 parses
   `pcb/temper.kicad_pcb`'s own Edge.Cuts geometry rather than trusting
   a `board_size:` string in the config; Gate 3 parses the board's own
   net table rather than trusting `elec/domain_manifest.yaml`, which
   only covers HV/SELV domains, a subset).
2. **Unsatisfiable is distinguished from unsatisfied, explicitly.** A
   reference to something that does not exist, or a value that
   structurally cannot be true (a zone off the board, a key matching no
   net), is a config defect and must fail the gate. A downstream
   system's *quality* result (does this placement satisfy this
   constraint) is a different, separately-owned question and must never
   be folded into the same gate -- conflating the two either makes the
   gate too noisy to trust (real placement tradeoffs reported as config
   defects) or too narrow to catch config defects (only checked when a
   placement run happens to touch that constraint).
3. **The gate is proven to catch its own motivating defect before it is
   considered done** -- against the real broken state if one still
   exists (Gates 1 and 3, above), or against a reconstructed/synthetic
   one if the defect predates any code that could produce it (Gate 2's
   pre-`c4956df66` board, and all three gates' synthetic-fixed-copy
   tests). A gate not proven to catch its own motivating defect is not a
   gate -- that failure mode was named as having occurred seven times in
   this repo's history before today's cluster.

Applying rule (b) retroactively to every hand-maintained mapping found
by survey is future work beyond this task's stated scope (the survey
itself, `HighVoltageIsolated`'s `class_order` gap, and the board-
dimension duplicates above, are named specifically so that work is
findable, not lost).
