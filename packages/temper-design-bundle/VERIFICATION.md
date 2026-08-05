# Net-type classification data model — Verification

The net-types data model (`src/net_types.rs`) is the Wave 4 Phase 2
"contracts-as-pyo3-pyclasses" pivot: the first contract migration, ported
from `temper_placer/core/net_types.py` (the Python module is now a
pure-delegation re-export of the `temper_design_bundle_python` pyclasses).

## Induction applicability

**Mathematical induction is not applicable to this module.** None of its
functions are recursive and none iterate over a dimension whose correctness
depends on a size parameter:

- `get_clearance_mm` / `get_creepage_mm` are single table lookups with a
  constant multiplier — no loop, no recursion.
- `NetTypeSpec::validate` is a fixed sequence of four disjoint branch tests
  over a fixed field set — the number of error classes is constant.
- `classify_net` / `get_plane_nets` / `get_pour_nets` / `validate_all` /
  `from_yaml_config` iterate over caller-provided collections
  (specs/patterns), but the per-element operation is independent of the
  collection's size and of the iteration order (verified by MR2 in
  `test_net_types_pbt.py` — insertion-order permutation invariance). There
  is no size-parameterized invariant to induct on.

The module is data-only (enums, one frozen dataclass, one plain dataclass,
pure string-parse helpers). Per the plan's R1e, a **structural proof** is
recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass
behaviour is bit-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/core/_net_types_py_oracle.py`,
commit `37a4251e0`).

*Proof by structural cases.*

1. **Enum tables (`get_clearance_mm`, `get_creepage_mm`).** Both sides are
   finite `match`/dict lookups over the same 5-member closed domain with the
   same base constants, scaled by the same IEEE-754 multipliers
   (`0.8 / 1.0 / 1.4 / 1.5`) for the same guard values. IEEE-754 double
   multiplication is deterministic across implementations, so each of the
   5 × 3 input combinations yields bit-identical doubles. Exhaustive
   coverage: the differential test drives every member × every degree/group,
   and P1/P1b re-assert the closed form independently.

2. **`validate` / `is_valid`.** The error corpus is produced by four
   pairwise-disjoint branch conditions, each transcribed verbatim from the
   oracle: (a) ground with non-plane/non-direct connectivity, (b) HV with
   creepage below the IEC minimum, (c) HV with clearance below the IEC
   minimum, (d) high-current or >5 A with `Via1x1`, (e) differential without
   impedance. Because the branches are disjoint, the output list is exactly
   the union of the firing branches — the same union the Python builds. The
   message text is byte-identical: enums format via the same
   `"MEMBER_NAME"` strings, and floats format with Rust `{:?}` (shortest
   round-trip) which equals Python `repr` for the closed set of values that
   can appear (the IEC table bases `{0.5, 1.0, 1.5, 1.6, 2.5, 3.0, 5.0, 8.0,
   14.0}` and caller-supplied mm/A values; all integral values gain `.0` in
   both). `is_valid` is the negation of the empty check in both sides.

3. **`classify_net`.** The triage is a deterministic first-match chain:
   explicit-spec lookup → ground patterns → power patterns → HV patterns →
   signal default. Both sides evaluate the same substring predicates on
   `net_name.upper()` in the same order; the returned spec is the same
   module constant (field-equal; the differential test documents that
   identity is not the contract). The pattern sets are the same six-element
   sets on both sides (the `frozenset`→`set` type change is documented and
   content-equal).

4. **`from_yaml_config`.** The mapping is a deterministic transcription of
   the oracle's per-rule default-resolution chain (`type` → class-name lower,
   `connectivity` → net-type default, HV `voltage_class` → `mains_240v`,
   `target_layer` → `LayerIndex` member, `max_current_a` →
   `max_current_rating` → 0.5, and the scalar defaults). The one non-obvious
   case — the `target_layer` default resolving to a `LayerIndex` IntEnum —
   is preserved exactly (not flattened to `int`) because
   `temper_placer/io/zone_manager.py` serializes the value with `str()` into
   the KiCad `(layer "…")` token; the pyclass imports
   `temper_placer.core.board` lazily at call time to construct the same
   IntEnum. This preserves the pre-migration observable behaviour
   (`str(LayerIndex.IN1_CU) == "In1.Cu"`), which a bare `int` would change
   to `"1"`.

5. **Module constants.** The four pre-defined specs (`GROUND_PLANE_SPEC` et
   al.) are built field-by-field from the oracle's literals; the differential
   test asserts field equality for all four.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/core/test_net_types_rust_differential.py`
  (43 assertions, oracle `_net_types_py_oracle.py`).
- PBT (R1c): `test_net_types_pbt.py` — 7 hypothesis properties
  (P1/P1b/P2/P3/P4/P5/MR1), vacuity-guarded.
- Metamorphic (R1d): `test_net_types_pbt.py` — MR1 (round-trip + kwarg-order
  commutativity), MR2 (insertion-order permutation invariance), MR3
  (from_yaml_config ≡ direct construction).
- Performance A/B (R1b): this is a pure-data contract migration with no
  compute kernel; the performance A/B is the "no regression beyond noise"
  comparison defined in the plan's R2 for delegation-only modules.

---

# Loop-centric data model — Verification

The loop data model (`src/loops.rs`) is the SECOND Wave 4 Phase 2
"contracts-as-pyo3-pyclasses" migration, ported from
`temper_placer/core/loop.py` (the Python module is now a pure-delegation
re-export of the `temper_design_bundle_python` pyclasses, mirroring the
net-types precedent).

## Induction applicability

**Mathematical induction is not applicable to this module.** None of its
functions are recursive and none iterate over a dimension whose correctness
depends on a size parameter:

- `estimated_inductance_nh` / `max_area_for_inductance_nh` /
  `voltage_spike_v` / `area_margin_pct` / `estimated_voltage_spike` are
  closed-form arithmetic — no loop, no recursion.
- `get_component_refs` / `involves_component` / `involves_net` and every
  `LoopCollection` query iterate over caller-provided lists, but the
  per-element operation is independent of the collection's size and of the
  iteration order (verified by MR2 in `test_loop_pbt.py` — insertion-order
  permutation invariance). There is no size-parameterized invariant to
  induct on.

The module is data-only (two string-valued enums, three dataclasses, one
container). Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass
behaviour is bit-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/core/_loop_py_oracle.py`,
commit `76f38db0a`).

*Proof by structural cases.*

1. **Enum tables (`LoopType`, `LoopPriority`).** Both sides enumerate the
   same closed member sets with the same string values in the same order.
   `name`/`value` mirror the Python `Enum` accessors; `str(member)` is
   `"LoopType.COMMUTATION"` and `repr(member)` is
   `<LoopType.COMMUTATION: 'commutation'>` (the value is QUOTED — the
   string-valued-enum rendering, verified by the differential test).
   Value-based construction `LoopType("commutation")` resolves by value
   exactly as Python `Enum(value)` does, including the exact `ValueError`
   text `'<value>' is not a valid LoopType`. Members are NOT equal to
   their string value and are hashable (plain-Enum semantics; no `eq_int`).

2. **`LoopEvent` physics.** `estimated_inductance_nh` computes
   `mu_0 * (A·1e-6) / (h·1e-3) * 1e9` with `mu_0 = 4·π·1e-7` — the
   oracle's expression shape preserved verbatim (B7: same three-op chain,
   no reassociation, no fusing), so every input yields bit-identical
   doubles (asserted on `.hex()` keys). `max_area_for_inductance_nh` and
   `voltage_spike_v` are the corresponding closed forms with the same
   property. The `None`-lifecycle (all fields default `None`; `voltage_spike_v`
   returns `None` without `di_dt`) matches the oracle.

3. **`LoopPin`.** Three fields with the same defaults; `__str__` produces
   `"Q1.GATE"` / `"Q1.GATE (NET)"` byte-identically.

4. **`Loop`.** Construction mirrors the dataclass default chain
   (`pins`/`components`/`nets` empty, `max_area_mm2=100.0`,
   `priority=MEDIUM`, `events=LoopEvent()`, `return_layer`/`return_net`
   `None`, `source="manual"`). `get_component_refs` returns the
   `components` list verbatim when non-empty, else unique pin refs in
   first-appearance order (dedup via an insertion-ordered scan — same
   algorithm the oracle's `seen`-set loop implements). The area lifecycle
   (`set_current_area`/`get_current_area`/`is_area_compliant`/
   `area_margin_pct`/`estimated_voltage_spike`) reproduces the oracle's
   `None`-until-set semantics and its exact arithmetic
   (`(max - area) / max * 100`).

5. **`LoopCollection`.** Construction, `add_loop` (including the
   duplicate-name `ValueError` text), every query, `summary` (same keys,
   same values), `__len__`/`__iter__`/`__getitem__` (int with negative
   wrap, str by name, `KeyError`/`TypeError`/`IndexError`) all mirror the
   oracle. Loops are stored as `Py<Loop>` handles so mutation through
   `collection[name].set_current_area(...)` is visible to subsequent
   queries — the pre-migration stored the same mutable objects.

6. **Documented deviations.** (a) pyo3 pyclass enums cannot support
   class-level iteration (`for lt in LoopType:`); the enums expose a
   `members()` staticmethod (declaration order) and `io/loop_loader.py` —
   the only consumer that iterated — was adapted to use it,
   behavior-identically (same members, same order, same error text).
   (b) `add_loop`'s Python parameter is named `new_loop` in Rust (`loop`
   is a Rust keyword); all callers pass it positionally.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/core/test_loop_rust_differential.py`
  (55 assertions, oracle `_loop_py_oracle.py`).
- PBT (R1c): `test_loop_pbt.py` — 5 hypothesis properties (P1–P5),
  each with a `test_pN_fails_for_<mutant>` vacuity mutant (G4 pattern via
  `hypothesis.inner_test` against a degenerate kernel) plus a deterministic
  vacuity anchor (`test_p3_components_win_over_pins`).
- Metamorphic (R1d): `test_loop_pbt.py` — MR1 (construction→access
  round-trip + kwarg-order commutativity), MR2 (insertion-order
  permutation invariance of set-valued collection queries), MR3
  (`Loop.estimated_voltage_spike` ≡ chained `LoopEvent` computation,
  bit-exact).
- Performance A/B (R1b): pure-data contract migration with no compute
  kernel; the "no regression beyond noise" comparison defined in the
  plan's R2 for delegation-only modules applies.

---

# Design-rules data model — Verification

The design-rules data model (`src/design_rules.rs`) is the THIRD Wave 4
Phase 2 "contracts-as-pyo3-pyclasses" migration, ported from
`temper_placer/core/design_rules.py` (the Python module is now a
pure-delegation re-export of the `temper_design_bundle_python` pyclasses,
mirroring the net-types and loop precedents).

## Candidate scorecard (why design_rules, not board/netlist)

The Phase 2 contract list (`docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`
line 97) names `core/board.py`, `core/netlist.py`, `core/loop.py`,
`core/design_rules.py`, `core/priority.py`, `core/net_types.py` among the
contracts. After net_types + loop, the three pure-data candidates were
design_rules (640 LOC, ~30 consumers incl. tests), board (803 LOC, 100+
consumers, numpy float32 array returns, `_test_only_2layer`), and netlist
(440 LOC, 100+ consumers, numpy `eigh`/spectral adjacency — not
bit-reproducible, per the prior scorecard's REJECT). board and netlist are
entangled beyond the R1 gate's honest reach (consumer counts an order of
magnitude over the landed migrations, non-reproducible numerics); design_rules
is the least-bad — its logic (lookup cascade, word-boundary classification,
via-template geometry) is pure and migratable, and its unmigrated leaves
(Pydantic `NetClassRules`, `DifferentialPairConstraint`, `BusCohortConstraint`,
`NetGraph`, `router_v6`'s ground/power recognizers) are held opaquely as
`Py<PyAny>`/`Py<PyDict>`, exactly the `LayerIndex` pattern from net_types.

## Induction applicability

**Mathematical induction is not applicable to this module.** None of its
functions are recursive and none iterate over a dimension whose correctness
depends on a size parameter:

- `ViaTemplate::get_footprint_bbox` / `get_via_positions` / `via_count` are
  closed-form arithmetic (a constant number of ops; the position loop is a
  fixed transcription of a 2-D grid whose per-element formula is independent
  of the grid size).
- `DesignRules::get_rules_for_net` is a fixed sequence of disjoint lookup
  tiers (override → assignment → class → 5-class pattern cascade → Default);
  `get_via_template` / `get_diff_pair_for_net` / `get_bus_cohort_for_net`
  iterate caller-provided collections, but the per-element operation is
  independent of the collection's size and of the iteration order (verified
  by MR3 in `test_design_rules_pbt.py` — override isolation, and the
  differential suite's mutation-path test). There is no size-parameterized
  invariant to induct on.

The module is data-only (one geometry dataclass, one mutable container
dataclass, plus Python-side constant tables). Per the plan's R1e, a
**structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass
behaviour is bit-identical to the pinned pre-migration Python implementation
(`packages/temper-placer/tests/core/_design_rules_py_oracle.py`, commit
`e5bd461e2`).

*Proof by structural cases.*

1. **`ViaTemplate` geometry.** Construction mirrors the 6-field dataclass
   (no defaults). `get_footprint_bbox` computes `(cols - 1) * pitch +
   diameter` / `(rows - 1) * pitch + diameter` — the oracle's expression
   shape preserved verbatim (B7: same op count, same grouping, no
   reassociation), so every input yields bit-identical doubles (asserted on
   `.hex()` keys in the differential suite and recomputed independently in
   P5). `get_via_positions` transcribes the oracle's `start = center -
   array/2.0`, `x = start + col * pitch` shape; `via_count` is `rows * cols`.
   `__eq__` is all-six-field `==`; `__repr__` renders floats with
   `py_float_str` and the name with `py_str_repr` (CPython `repr(str)` is
   single-quoted; Rust `{:?}` is double-quoted — the differential test pins
   the full repr strings, so this divergence would have failed it).

2. **Word-boundary classifier (`_hv_word_boundary_match`).** Transcribed
   into native Rust string logic. The oracle's patterns are fixed
   `[A-Za-z0-9_]` constants (`("GATE", "SW_NODE")`, `("PWM",)`,
   `("DC_BUS", "AC_L", "AC_N", "COIL")`), so `re.escape` is the identity and
   a literal-substring transcription of `(?:^|_){p}(?:$|[\d_])` is exact.
   The 2026-07-27 bug case (`"COIL"` must NOT match
   `discharge.k_dis1-coil1`, preceded by `-`) is asserted in the Rust unit
   tests AND exercised by the differential/PBT suites; P3 compares the whole
   cascade against an independent reference transcription. Documented
   deviation: CPython `\d` matches Unicode digits; this transcription is
   ASCII-only. Net names in the repo are ASCII and every exercised input is
   ASCII, so the two agree on the tested surface — recorded here as a
   standing divergence to re-check if a Unicode net name ever enters the
   classifier.

3. **`DesignRules` lookup cascade (`get_rules_for_net`).** The five tiers
   are transcribed in the oracle's exact order and short-circuit semantics:
   per-net override → `net_class_assignments` (only when no class argument)
   → explicit class → ground → power → gate-HV → gate-SELV → high-current
   (each pattern tier gated on the class being present) → Default catch-all.
   `_is_ground_net`/`_is_power_net` delegate to
   `router_v6.net_classification` via the same lazy import the oracle makes
   — those functions consult the `_SINGLE_LAYER_MODE` module-global, so a
   native reimplementation would diverge on that state (this is the
   `LayerIndex`-style opaque delegation, documented in the module docstring).
   The Default catch-all constructs the same Pydantic `NetClassRules`
   (`name="Default"`, the instance's scalar fields, `dru_priority=999`)
   through the unmigrated model, so the returned object is field-identical.

4. **`DesignRules` mutability contract.** Consumers mutate the dataclass in
   place (`dr.net_classes[x] = …`, `dr.differential_pairs.append(…)`,
   `dr.net_topologies[x] = …`, scalar assignment, and the dynamically-
   attached `dr.class_pairs`). The pyclass stores every container as the
   actual Python `dict`/`list` object (`Py<PyDict>`/`Py<PyList>`) with
   explicit getters AND setters, so in-place mutation and whole-field
   assignment persist exactly like the dataclass; `class_pairs` defaults to
   an empty dict so `getattr(dr, "class_pairs", {})` behaves as before. The
   differential suite's `test_mutation_paths_persist_identically` drives the
   same mutation sequence through both sides and asserts field-identical
   results, and the existing consumer tests
   (`tests/io/test_netclass_loader.py`, `test_config_board_binding.py`) pass
   unchanged against the pyclass.

5. **`__eq__` / `__repr__`.** Equality is all-field `==` with the container
   fields compared via Python `==` (element-wise, matching dict/list
   equality); `class_pairs` is not a dataclass field and does not
   participate — exactly like the oracle. Repr renders the container fields
   through Python `repr` (so the Pydantic objects and dict ordering render
   identically) and floats via `py_float_str`; the differential test asserts
   full repr-string equality.

6. **Module constants stay Python.** `TEMPER_NET_CLASSES`,
   `TEMPER_NET_ASSIGNMENTS`, `SAFETY_CONSTANT_AUTHORITY` construct Pydantic
   `NetClassRules` objects and remain in the delegation module (verbatim
   construction code); `test_module_constants_identical` pins them
   field-identical to the oracle. Documented deviation: the stray
   `print("DEBUG: Loading design_rules.py")` class-body statement from the
   pre-migration module is gone (a debug artifact with no API surface); the
   oracle retains it verbatim.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/core/test_design_rules_rust_differential.py`
  (29 assertions, oracle `_design_rules_py_oracle.py`).
- PBT (R1c): `test_design_rules_pbt.py` — 5 hypothesis properties (P1–P5),
  each with a `test_pN_fails_for_<mutant>` vacuity mutant (G4 pattern via
  `hypothesis.inner_test` against a degenerate kernel).
- Metamorphic (R1d): `test_design_rules_pbt.py` — MR1 (construction→access
  round-trip + kwarg-order commutativity), MR2 (`get_class_for_net` ≡
  `get_rules_for_net(net).name`), MR3 (override isolation — perturbing one
  net leaves every other net's resolution unchanged).
- Performance A/B (R1b): pure-data contract migration with no compute
  kernel; the "no regression beyond noise" comparison defined in the plan's
  R2 for delegation-only modules applies.

# Gate-contract data model — Verification

The gate-contract data model (`src/gates.rs`) is the FOURTH Wave 4 Phase 2
"contracts-as-pyo3-pyclasses" migration, ported from
`temper_placer/placer/cp_sat/gates.py` (the Python module is now a
pure-delegation re-export of the `temper_design_bundle_python` pyclasses,
mirroring the net-types, loop, and design-rules precedents).

## Candidate scorecard (why gates, not pcl/constraints / routing_results / protocol)

The plan's Phase B surface (`docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`)
names, beyond core/, the gate-contract types, the constraint IR, routing
results, and the protocol types. Scored:

| Candidate | LOC | Consumers (src) | Purity | Verdict |
|-----------|-----|-----------------|--------|---------|
| `placer/cp_sat/gates.py` contract types | ~85 (of 1143; the rest is gate implementations that stay Python) | 12 src + 20+ tests | 3 string enums + 3 frozen dataclasses, zero compute | **SELECTED** |
| `pcl/constraints.py` IR | 872 | 36 | `SeparatedConstraint`/`AnchoredConstraint`/`BaseConstraint` are entangled with the ortools encoder (they construct encoder objects); `ConstraintTier` is a plain enum but the module's import graph pulls the encoder | JUSTIFIED-KEEP — encoder entanglement beyond the honest R1 reach |
| `router_v6/routing_results.py` | 233 | 13 | `CompiledRoute`/etc. fields HOLD router_v6 runtime types (`RoutePath3D`, `PathfindingResult`, `NetConnectivity`, `ViaPlacement`, ... — 6 imports from astar/connectivity/trace modules) | JUSTIFIED-KEEP — the dataclasses are containers over unmigrated runtime types |
| `protocol.py` | 141 | 7 | mixes type defs with runtime constants | NOT SELECTED — smaller surface, no consuming kernel; revisit later |

gates.py's contract types are pure data (three string-valued enums, three
frozen dataclasses whose opaque payload fields are held as the exact Python
objects) with the gate *implementations* (`Gate` and subclasses — DrcGate,
RoutingGate, StackupGate, IECCreepageGate, PhysicsGate, QualityGate, ErcGate)
staying Python in the delegation module (they run subprocesses/kicad-cli and
are not data contracts), plus `_VIOLATION_TYPE_MAP`/`_map_violation_type`
(stays Python — resolves kicad-cli DRC type strings onto `ViolationType`
members).

## Induction applicability

**Mathematical induction is not applicable to this module.** None of its
functions are recursive, and none iterate over a dimension whose correctness
depends on a size parameter:

- The enums are finite constant sets; `members()` emits them in declaration
  order (a fixed transcription, independent of any size).
- `Violation.__eq__`/`__hash__`/`__repr__` are fixed-arity field walks over
  the seven declared fields; `GateResult` and `BoardState` likewise. The
  `context` dict/tuple contents are compared via Python's own `==`/`repr()`
  on the held objects (the per-element operation is independent of the
  container's size and order).

The module is data-only (three enums, three frozen dataclasses, no compute
kernel). Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass
behaviour is bit-identical to the pinned pre-migration Python implementation
(`packages/temper-placer/tests/placer/cp_sat/_gates_py_oracle.py`, commit
`ef2ac25fd`).

*Proof by structural cases.*

1. **Enum parity (`GateStatus`, `GateStage`, `ViolationType`).** The pyo3
   enums are PLAIN Python `Enum`s with string values (not IntEnum): members
   are not equal to their value. `#[new]` resolves `Enum(value)` by string
   value with the exact `ValueError` text; `name`/`value` getters, `__str__`
   (`GateStatus.CLEAN`), and `__repr__` (`<GateStatus.CLEAN: 'clean'>` — the
   string value QUOTED via `py_str_repr`) mirror CPython. `members()` is the
   pyo3 substitute for class-level iteration (`list(GateStatus)`); every
   consumer and test that iterated the enums was adapted to it
   (test_gate_contract.py, test_gates_pbt.py, test_gates_rust_differential.py).
   Enum *identity* is load-bearing: consumers compare `result.status is
   GateStatus.CLEAN` / `violation.type is ViolationType.CREEPAGE` (delta_mapper,
   fields/result.py, _loop_gates.py, _pipeline_core.py). pyo3 caches members
   as class attributes and the dataclasses hold them opaquely as `Py<PyAny>`,
   so attribute access AND getter return the exact cached object
   (asserted: `E.M is E.M`, `getattr(E, 'M') is E.M`, `v.type is
   ViolationType.CREEPAGE`, `bs.status is GateStatus.CLEAN`).
   **Documented deviation:** `Enum(value)` returns an equal-but-distinct
   instance (the pyo3 `#[new]` constructor cannot return the cached member
   object), where the pre-migration Python Enum returned the cached
   singleton. No consumer value-constructs for identity (`==` is used; the
   only `is`-dispatch is on attribute access / held fields, which ARE
   identity-stable). Recorded here per R1's deviation rule; asserted
   explicitly in P4.

2. **`Violation`.** Construction mirrors the 7-field frozen dataclass with
   defaults `()`/`()`/`0.0`/`0.0`/`""`/fresh `dict` per instance
   (`field(default_factory=dict)` — two default instances never share a
   context dict, asserted). The `type` field is unvalidated (any object is
   held — the oracle does not cast), and the container fields are the actual
   Python objects, so `v.type is ViolationType.X` holds end to end.
   `__eq__` is all-seven-field `==` (floats via IEEE `==`, so NaN != NaN on
   both sides); `__hash__` builds the canonical Python tuple and calls
   Python's own `hash()` — reproducing the dataclass's `TypeError` when a
   field is unhashable (every `Violation`'s `context` dict makes it
   unhashable, exactly like the dataclass; asserted on both sides).
   `__repr__` renders floats with `py_float_str` (B10: `1e-05`/`1e+300`/
   `nan` — Rust `{:?}` writes `1e-5`/`1e300`/`NaN`), the description with
   `py_str_repr` (B9: single quotes), and the enum member/tuples/dict via
   Python's own `repr()` on the held objects — byte-identical, asserted
   full-string.

3. **`GateResult`.** Construction mirrors the 3-field frozen dataclass
   (defaults `()`/`""`). The oracle's `__post_init__` invariant — a
   `VIOLATIONS` status with an empty `violations` tuple raises
   `ValueError("GateResult with status=VIOLATIONS must have at least one
   Violation")` — is enforced in `#[new]` using IDENTITY against the cached
   `GateStatus.VIOLATIONS` member (`py.get_type::<GateStatus>()` +
   `getattr("VIOLATIONS")` + `Bound::is`), exactly the oracle's
   `self.status is GateStatus.VIOLATIONS`; the exact message text is
   asserted on both sides. `__eq__`/`__hash__`/`__repr__` follow the
   Violation case (status and the violations tuple via Python's own
   semantics — the tuple repr recurses through each `Violation.__repr__`).

4. **`BoardState`.** Construction mirrors the 6-field frozen snapshot
   dataclass with all-`None` defaults. Every field is an opaque payload held
   as the exact Python object (`Py<PyAny>`), so `bs.board is board` identity
   holds and gates inspect the payload objects directly (asserted). `__eq__`
   is all-six-field `==`; `__hash__` is the Python tuple-hash (unhashable
   payloads raise `TypeError`, exactly like the dataclass); `__repr__`
   renders each payload via Python's own `repr()` (`None` as `None`, a `Path`
   as `PosixPath('/tmp/...')`).

5. **The gate implementations stay Python.** `Gate` and its subclasses
   (DrcGate, RoutingGate, StackupGate, IECCreepageGate, PhysicsGate,
   QualityGate, ErcGate), `_VIOLATION_TYPE_MAP`, and `_map_violation_type`
   remain in the delegation module verbatim — they run subprocesses/kicad-cli
   and resolve DRC type strings, and are not data contracts. The delegation
   module re-exports the pyclasses under the pre-migration names, so
   `from temper_placer.placer.cp_sat.gates import GateStatus, ...` is
   unchanged for every consumer (verified: all 12 src consumers import the
   module and pass unchanged; the identity `is`-dispatch sites in
   fields/result.py, delta_mapper.py, _loop_gates.py, _loop_stability.py,
   _pipeline_core.py, thermal_fdm.py, battery_run.py are covered by the
   consumer suites below).

6. **`__hash__` presence.** pyo3's `frozen` keeps `__hash__` available
   (frozen dataclasses define `__hash__`). The tuple-hash replication means
   hashability tracks the oracle exactly (a `GateResult` carrying a
   `Violation` is unhashable on both sides — asserted).

## Documented deviations (per R1, recorded here)

- `Enum(value)` returns an equal-but-distinct instance (see §1) — no
  consumer relies on value-construction identity.
- The pyclasses raise `AttributeError` on attribute assignment where the
  dataclasses raised `dataclasses.FrozenInstanceError` (a subclass of
  `AttributeError` — same base class); test_gate_contract.py's frozen tests
  were updated to `pytest.raises(AttributeError)`.
- `severity`/`threshold` are typed `f64`: an `int` passed pre-migration
  stayed an `int` (repr `1`), here it coerces to `1.0` (repr `1.0`). No
  consumer passes ints (every construction site uses float literals); the
  differential/PBT suites drive floats.
- `members()` replaces class-level Enum iteration; `__members__`-style
  iteration is unavailable on pyclasses. All in-repo iteration sites were
  adapted.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/placer/cp_sat/test_gates_rust_differential.py`
  (oracle `_gates_py_oracle.py`, commit ef2ac25fd; enum identity, the
  VIOLATIONS invariant with exact message, unhashability, and full
  `repr(...)` equality byte-for-byte, per case and pinned as a union).
- PBT (R1c): `test_gates_pbt.py` — 5 hypothesis properties (P1–P5), each
  with a `test_pN_fails_for_<mutant>` vacuity mutant (G4 pattern via
  `hypothesis.inner_test` against a degenerate kernel).
- Metamorphic (R1d): `test_gates_pbt.py` — MR1 (construction→access
  round-trip + kwarg-order commutativity), MR2 (canonical-form ⇔ equality),
  MR3 (enum construction commutation: `Cls(member.value) == member`), MR4
  (BoardState payload independence).
- Rust unit tests: `gates.rs::repr_helper_tests` pins the B9/B10 rendering
  divergence classes (`1e+300`, `1e-05`, `nan`, single-quote escaping).
- Performance A/B (R1b): pure-data contract migration with no compute
  kernel; the "no regression beyond noise" comparison defined in the plan's
  R2 for delegation-only modules applies.
- Consumer suites run unchanged against the pyclasses: test_gate_contract.py,
  test_delta_mapper.py, test_loop_field_feedback.py, test_compound_loop.py,
  test_finish_board_gate.py, test_phase1_anti_false_zero.py, and the
  fields/physics suites listed in the migration PR.

# Priority-classification data model — Verification

The priority data model (`src/priority.rs`) is the FIFTH Wave 4 Phase 2
"contracts-as-pyo3-pyclasses" migration, ported from
`temper_placer/core/priority.py` (the Python module is now a pure-delegation
re-export of the `temper_design_bundle_python` pyclasses, keeping
`POWER_STAGE_TEMPLATES` and the `classify_net_priority` convenience wrapper
Python per the gates-migration precedent).

## Candidate scorecard (why priority, not the KEEP'd Phase-2 surfaces)

The remaining named Phase-2 contract surfaces were scored under R3 (recorded
2026-08-03 in the plan's Phase 2 residual-decisions section); this migration
is the one surface that cleared the R1 honest-reach bar:

| Candidate | LOC | Consumers (src) | Purity | Verdict |
|-----------|-----|-----------------|--------|---------|
| `core/priority.py` | 203 | 2 (core/__init__ re-export + heuristics/power_stage.py) | 2 IntEnums + 3 dataclasses, self-contained string heuristics, stdlib-only | **SELECTED** |
| `pcl/constraints.py` IR | 872 | 32 | ortools-encoder entangled (9 cp_sat handlers construct encoder objects; bridges register into the class-level `BaseConstraint.backends` registry); `CompilationContext` holds unmigrated Netlist/Board/ChannelSkeleton/ChannelWidths/DesignRules | JUSTIFIED-KEEP — encoder entanglement beyond the honest R1 reach |
| `router_v6/routing_results.py` | 233 | 18 | `CompiledRoute`/`RoutingResults` fields HOLD unmigrated router_v6 runtime types (RoutePath, RoutePath3D, TreeRouteGeometry, NetConnectivity, ViaPlacement, NetRoutingReport, ... — 9 imports) | JUSTIFIED-KEEP — containers over unmigrated runtime types |
| `protocol.py` | 141 | 7 | `@runtime_checkable` structural Protocol + `dict[str, type]` isinstance schema + exception; orchestration seam | JUSTIFIED-KEEP — structural-typing/type-object semantics have no pyclass mapping; Phase 5 |
| `core/board.py` / `core/netlist.py` | 803 / 440 | 100+ | numpy float32 array fields / numpy `eigh` spectral adjacency (not bit-reproducible); Board is produced by the Phase 3 KiCad parser | JUSTIFIED-KEEP — D5 dependency rationale (formats first); re-decide at Phase 3 pull |

## Induction applicability

**Mathematical induction is not applicable to this module.** None of its
functions are recursive and none iterate over a dimension whose correctness
depends on a size parameter:

- `PlacementPriority`/`RoutingPriority` are finite constant sets; `Cls(v)`
  construction and the `name`/`value` getters are fixed transcriptions.
- `PriorityConfig::classify_component` is a fixed sequence of disjoint
  prefix tests after a constant digit-strip; `classify_net` is a fixed
  sequence of disjoint keyword/substring tests. `_kw_boundary_match` (ported
  as `kw_boundary_match`) scans literal keyword occurrences — the per-
  occurrence boundary test is independent of the string's length and of
  which occurrence matches first (the boolean result is order-independent;
  verified by MR1/MR4 in `test_priority_pbt.py`).
- `get_placement_phase`/`get_routing_phase` iterate caller-provided phase
  lists, but the per-element comparison is independent of the list's size
  and — with distinct priorities — of its order (verified by MR2).

The module is data-only (two int enums, two phase-config dataclasses, one
container with closed-form classification). Per the plan's R1e, a
**structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass
behaviour is bit-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/core/_priority_py_oracle.py`,
commit `a47527751`).

*Proof by structural cases.*

1. **Enum parity (`PlacementPriority`, `RoutingPriority`).** The pyo3
   enums are Python `IntEnum` replicas: int-valued members exposed as cached
   class attributes, `name`/`value` getters, `Cls(value)` construction with
   the exact CPython `ValueError` text (`999 is not a valid
   PlacementPriority`), `str(member)` = `int.__str__` (`"1"`), and
   `repr(member)` = `<PlacementPriority.POWER: 1>`. The value tables
   (`POWER=1 .. DIGITAL=5`, `AUTO=10`) are pinned verbatim; the differential
   suite asserts every member's name/value/str/repr on both sides, and P4
   pins the (name, value) bijection against a fixed table.

2. **`PlacementPhaseConfig` / `RoutingPhaseConfig`.** Construction mirrors
   the dataclass signatures with identical defaults (`method="optimize"`,
   `max_distance_mm=20.0`, `trace_width_mm=0.25`, `via_cost=1.0`,
   `allow_layer_change=True`, fresh `list` per instance — never shared).
   `__eq__` is all-fields `==` (floats via IEEE `==`, so NaN != NaN on both
   sides); the pyclasses are unhashable exactly like the mutable dataclasses
   (no `#[pyclass(hash)]`). `__repr__` renders strings with `py_str_repr`
   (B9: single quotes), floats with `py_float_str` (B10: `1e+300`/`1e-05`/
   `nan`), the priority enum with its `py_repr`, and the bool with CPython's
   `True`/`False` — byte-identical, asserted full-string.

3. **`PriorityConfig`.** Construction mirrors the two-list dataclass
   (fresh lists per instance); phases are held as `Py<PlacementPhaseConfig>`
   / `Py<RoutingPhaseConfig>` handles so consumer-side mutation is visible
   to the queries, matching the pre-migration shared-object semantics.
   `get_placement_phase`/`get_routing_phase` replicate the oracle's
   first-match-`find` (order-dependent only for duplicate priorities, which
   MR2's distinct-priority bound excludes). `classify_component` replicates
   the oracle exactly: explicit-assignment scan first, then
   `ref.rstrip("0123456789")` (ported as
   `trim_end_matches(is_ascii_digit)`) and the four prefix tables in order;
   the unused `_netlist` argument is accepted and ignored. `classify_net`
   replicates the oracle exactly: explicit exact/wildcard pattern scan
   first, then `upper()`, then the four keyword/substring tiers in order.

4. **`kw_boundary_match` (port of `_kw_boundary_match`).** The oracle
   compiles `(?:^|_)<re.escape(kw)>(?:$|[\d_])` and `re.search`es it.
   Python's `re.escape` leaves ASCII letters/digits/underscore untouched, so
   the escaped pattern matches the raw keyword as literal text; the port
   scans every literal occurrence of the keyword and applies the same
   boundary conditions (preceded by start or `_`; followed by end, digit,
   `_`, or — pattern A — anything). Python's `$`-matches-before-a-trailing-
   newline rule is replicated (`"BUS\n"` matches, `"BUS\nX"` does not; Rust
   unit-tested). Because the boolean is "any occurrence matches" and a
   match's before/after chars are tested per occurrence, the overlap-skipping
   scan finds every match the regex would; equivalence is pinned by the
   differential suite's bug-history regression set (BUSTER/BUSBAR/BHV/ABUS
   negatives, `+15V` regex-special keyword, boundary positives) and the Rust
   unit tests.

5. **Module-level constants.** `POWER_STAGE_TEMPLATES` and the
   `classify_net_priority` wrapper stay in the delegation module (they are
   data / delegation, not contracts); `classify_net_priority` delegates to
   the pyclass and is pinned against the oracle by the differential suite.

## Documented deviations (per R1, recorded here)

- **IntEnum int equality:** Python `IntEnum` members compare `==` to their
  int value (`PlacementPriority.POWER == 1` is True); the pyclass members
  are NOT equal to ints. Verified no consumer relies on it (2026-08-03: no
  `PlacementPriority.* == <int>` / `<int> == PlacementPriority.*`
  expressions anywhere in `src/` or `tests/`).
- **Cross-enum `==`:** Python IntEnum falls back to int comparison across
  enum classes (`PlacementPriority.POWER == RoutingPriority.POWER` is True);
  pyo3 `#[pyclass(eq)]` compares only same-typed instances, so the pyclass
  returns False. No consumer compares across the two enums.
- **Class-level iteration** (`for p in PlacementPriority:`) is unavailable on
  pyo3 enums (no metaclass hook); the differential suite accesses members via
  `getattr`, and no consumer iterates these enums at class level.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/core/test_priority_rust_differential.py`
  (oracle `_priority_py_oracle.py`, commit a47527751; 87 assertions — enum
  name/value/str/repr/value-construction, dataclass defaults/round-trip,
  full `repr(...)` equality byte-for-byte, `classify_component` across every
  prefix branch, `classify_net` across every keyword/substring branch plus
  the 2026-07-27 word-boundary regression set, `classify_net_priority`
  delegation parity). RED first: the test failed to collect before the
  pyclasses existed.
- PBT (R1c): `test_priority_pbt.py` — 5 hypothesis properties (P1–P5), each
  with a `test_pN_fails_for_<mutant>` vacuity mutant (G4 pattern via
  `hypothesis.inner_test` against a degenerate kernel: bogus-value return,
  prefix-only classification, skipped explicit patterns, wrong enum value,
  always-None lookup).
- Metamorphic (R1d): `test_priority_pbt.py` — MR1 (prefix-decoration
  invariance, exact), MR2 (phase-list order independence, distinct
  priorities), MR3 (digit-suffix invariance, exact), MR4 (case invariance,
  exact), plus a vacuity-sanity test proving the default-config input space
  is genuinely discriminating (5 distinct classes on 6 nets).
- Rust unit tests: `priority.rs::py_repr_tests` (B9/B10 rendering classes)
  and `kw_boundary_tests` (the classify-net keyword set, regex-special `+`,
  `$`-before-trailing-newline, empty-keyword skip).
- Performance A/B (R1b): pure-data contract migration with no compute
  kernel; the "no regression beyond noise" comparison defined in the plan's
  R2 for delegation-only modules applies.
- Consumer suites run unchanged against the pyclasses: heuristics/power_stage
  and the `core/__init__.py` re-export path (verified in the migration PR).

---

# Board / netlist parse-target contracts — Verification

The board and netlist data models (`src/board_contracts.rs`,
`src/netlist_contracts.rs`) are Wave 4 **Phase 3, candidate 1** — the
dependency spine of the phase (candidates 3, 4 and 5 wait on it), ported
from `temper_placer/core/board.py` (803 LOC) and
`temper_placer/core/netlist.py` (440 LOC). Both Python modules are now
delegation shims that re-export the pyclasses and keep exactly two surfaces
Python, under the R3 verdicts recorded below.

This section supersedes the "JUSTIFIED-KEEP — re-decide at Phase 3 pull" row
for `core/board.py` / `core/netlist.py` in the priority-migration scorecard
above. That row cited two blockers: "numpy float32 array fields" and "numpy
`eigh` spectral adjacency (not bit-reproducible)". The first is
**overturned** — see case 7 of the structural proof. The second is
**upheld**, and is R3 #2 below.

## R3 verdicts (named blockers)

Per D6, a well-evidenced "this part cannot reach honest R1" is a legitimate
outcome. Two surfaces inside the candidate's scope are recorded as R3 rather
than forced or silently deferred.

### R3 #1 — `LayerIndex` and its derived tables stay Python

**Blocker: pyo3 cannot produce a pyclass that subclasses `int`.**

`LayerIndex` is a Python `IntEnum`, and its int-ness is load-bearing in this
repo, not incidental:

| Consumer | Expression | Requires |
|---|---|---|
| `router_v6/constraints_drc_oracle.py:532` | `LayerIndex(layer) in INTERNAL_LAYERS` | value construction + set membership by int hash |
| `deterministic/stages/_grid_hv.py:59` | `LAYER_IDX_TO_NAME[LayerIndex(layer_idx)]` | dict keying interchangeable with `int` |
| `net_types.rs:888` (already-migrated Rust) | `getattr(board, "LayerIndex")` → stored as `NetTypeSpec.target_layer: Py<PyAny>` | `==` against layer-name `str` AND against `int` |

pyo3's `extends=` accepts only fixed-basicsize bases; `int` is
variable-sized, so no pyclass can inherit from it. A pyo3 `#[pyclass]` enum
would therefore satisfy `LayerIndex.F_CU.value == 0` but **not**
`LayerIndex.F_CU == 0`, and `hash(LayerIndex.IN1_CU) != hash(1)`. That is
precisely the failure mode the plan warns about: a value-level differential
comparing `.name`/`.value` would pass while `{LayerIndex.IN1_CU: x}[1]`
started raising `KeyError` in production.

The fifth Phase-2 migration accepted the analogous deviation for
`PlacementPriority`/`RoutingPriority` because *no consumer relied on the int
comparison*. Here three do, so the same deviation is not available, and the
enum, its derived tables (`STANDARD_LAYER_ORDER`, `PLANE_LAYER_INDICES`,
`LAYER_IDX_TO_NAME`, `LAYER_NAME_TO_IDX`, `CANONICAL_4LAYER_LAYER_NAMES`,
`CANONICAL_LAYER_COUNT`) and the predicates that dispatch on it
(`is_plane_layer`, `is_signal_layer`, `layer_name_to_index`) remain Python.
`side_to_layer_name` does *not* touch `LayerIndex` and **was** migrated.

Guarded by
`test_board_rust_differential.py::test_layer_index_stays_a_python_intenum_r3`,
which asserts the int-ness directly — so a later attempt to move it must
confront this record rather than slip past it.

### R3 #2 — `compute_eigenvector_centrality` stays Python

**Blocker: `numpy.linalg.eigh` is LAPACK `?syevd`.**

The function returns the leading eigenvector of the adjacency matrix. No
independent implementation reproduces LAPACK's output bit-for-bit: an
eigenvector is defined only up to sign, and within a degenerate eigenvalue
subspace only up to an arbitrary rotation — both of which LAPACK resolves by
implementation-specific pivoting, not by a specified rule. A differential
could therefore only pass by *calling numpy from Rust*, which adds a
boundary crossing and proves nothing.

This is the same judgment PR #688 made in keeping `yaml.safe_load` on the
Python side rather than re-tokenizing: the migration stops where equivalence
stops being provable. The function has **zero in-repo consumers outside its
own module**, so nothing downstream is held back by leaving it.

Guarded by
`test_netlist_rust_differential.py::test_compute_eigenvector_centrality_stays_python_r3`.

## Induction applicability

**Mathematical induction is not applicable to these modules.** They are data
contracts; no function is recursive, and no function's correctness depends
on a size parameter:

- Every constructor, getter and `repr`/`__eq__`/`__hash__` is a fixed
  transcription over a fixed field list.
- The geometric methods (`Zone.width`/`height`/`center`/`area`, `Board.area`,
  `Rect.width`/`height`, `Board.contains_point`) are closed-form arithmetic
  on a constant number of operands.
- The methods that *do* loop (`Board.get_zone_for_point`,
  `Board.point_in_keepout`, `Netlist.build_indices`, `Netlist.validate`,
  `Component.get_pin`, `build_adjacency_matrix`) iterate caller-provided
  collections where the per-element operation is independent of the
  collection's size. Two of them are additionally *order*-independent, which
  is asserted rather than assumed: MR3 in `test_netlist_pbt.py` (net
  permutation leaves the adjacency matrix bit-identical) and MR4 in
  `test_board_pbt.py` (zone-list reversal changes `_zone_map` collisions
  identically on both sides).
- `Netlist.find_isomorphic_groups` iterates a caller-supplied `iterations`
  count, but each round is a pure relabelling whose per-node result depends
  only on the previous round's labels — a fold, not an induction over a
  correctness-carrying dimension. Parity is asserted for every
  `iterations ∈ {0, 1, 2, 3}` in both the differential and P8.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity, including the concrete Python type of every
field and the dtype of every returned array).** For every public symbol, the
pyclass behaviour is bit-identical to the pinned pre-migration Python
implementations (`tests/core/_board_py_oracle.py`, commit `5a17025b1`;
`tests/core/_netlist_py_oracle.py`, commit `e799183c4`).

*Proof by structural cases.*

1. **Field storage — type preservation by construction.** The pre-migration
   contracts are plain `@dataclass`es, which coerce nothing:
   `Component("R1", "fp", (1, 2))` stores `int` bounds and `.width` returns
   `int` `1`. Every pyclass field is therefore declared `Py<PyAny>` and
   stores *the caller's object itself*. There is no Rust-side numeric
   conversion anywhere on the construction path, so widening `int`→`float`
   or `f32`→`f64` is not merely untested but **unrepresentable**. The one
   place the oracle *does* coerce (`Rect.from_xyxy`/`from_xywh`/`coerce`
   call `float(...)`) is reproduced by calling CPython's own `float` type
   constructor, so `__float__`/`__index__`/`float("1.5")` all behave
   identically.

2. **Container identity.** Mutable container fields (`Net.pins`,
   `Component.pins`, `Board.zones`, `Board.keepouts`, `Zone.net_classes`,
   `Component.attributes`, …) are stored and returned as the *same* Python
   object, so in-place mutation still lands. This is load-bearing:
   `io/_parse_nets.py:50` builds every net by
   `nets_dict[pin.net].pins.append(...)`. A getter returning a fresh list
   would have produced empty nets across the whole parser while a
   value-equality differential stayed green — so it is asserted directly
   (`test_net_pins_list_is_shared_by_identity`, which checks the *caller's*
   list object is the stored one). `field(default_factory=...)` freshness is
   asserted symmetrically (`test_*_default_containers_are_fresh_per_instance`).

3. **`__repr__`.** Rather than re-deriving CPython's `repr(float)` /
   `repr(str)` rules (the `py_float_str`/`py_str_repr` helpers earlier
   Phase-2 migrations needed), each pyclass calls **CPython's own `repr()`**
   on each stored field and splices the results into the generated-dataclass
   layout `Cls(f1=r1, …, fn=rn)`. Since the field objects *are* the oracle's
   field objects, the rendered text is identical by construction for every
   value, including `1e+300`, `1e-05`, `nan`, `-0.0` and subnormals. The
   `repr=False` fields (`Netlist._component_index`, `_net_index`,
   `_component_nets`) are omitted, and the `init=False` but `repr=True`
   field `Board._zone_map` is included — both asserted.

4. **`__eq__` / `__hash__`.** `__eq__` builds the `compare=True` field tuple
   on both operands and defers to Python `==` on tuples, after the
   `other.__class__ is self.__class__` identity gate a generated dataclass
   `__eq__` applies (returning `NotImplemented` otherwise). Frozen classes
   (`Trace`, `Via`, `LayerStackup`) hash via `hash(tuple(fields))`, which
   reproduces the oracle exactly *including its failures*:
   `hash(LayerStackup.default_4layer())` raises
   `TypeError: unhashable type: 'Layer'` because `Layer` is a non-frozen
   dataclass whose `__hash__` is `None`. The mutable classes raise the same
   `TypeError` with the bare class name — pyo3's default message
   interpolates the dotted `tp_name`, so `__hash__` is written explicitly to
   keep the text byte-identical. `Rect` carries `eq=False` and keeps its
   hand-written `__eq__` (equal to a bare 4-`tuple`/`list`,
   `NotImplemented` otherwise) and `__hash__`, while still getting the
   generated `__repr__`; all three are reproduced separately.

5. **Frozen semantics.** `Trace`, `Via`, `LayerStackup` and `Rect` raise
   CPython's own `dataclasses.FrozenInstanceError` (imported from
   `dataclasses` at call time, not re-declared) with the exact
   `cannot assign to field 'x'` / `cannot delete field 'x'` text. A pyclass
   field without `set` would have raised a different type *and* message.

6. **Arithmetic.** Every derived value is computed through Python's own
   operators (`PyAnyMethods::add`/`sub`/`mul`/`div`/`pow`), never through
   Rust `f64`. So `Board(3, 4).area` is `int` `12` (not `12.0`),
   `Zone.center` is true division (always `float`), and IEEE-754 rounding is
   CPython's own. Chained comparisons (`0 <= x <= width`) are written out
   with their short-circuit preserved, so a probe that would raise on the
   second comparison only raises when the first succeeded.

7. **numpy arrays — the float32 surface.** `polygon_array`,
   `Board.get_bounds_array`, `Board.get_relative_bounds_array`,
   `Netlist.get_bounds_array`, `Netlist.get_fixed_mask` and
   `build_adjacency_matrix` are materialized by calling **numpy itself**
   (`numpy.array(obj, dtype=numpy.float32)`) with the identical argument
   object the oracle builds. The dtype and every element's bit pattern are
   therefore numpy's own; there is no Rust float conversion in the path that
   could widen `float32` to `float64`. This is what overturns the earlier
   "numpy float32 array fields" blocker: the fields were never the problem —
   re-implementing numpy's cast would have been, and it is not done. (The
   hypothesis corpus reaches the `float64`→`float32` overflow boundary and
   both sides emit the same `RuntimeWarning: overflow encountered in cast`
   and the same `inf` bytes.)

   The distinct empty-path dtypes are preserved verbatim, including the
   inconsistent one: `Netlist().get_bounds_array()` is `float32` shape
   `(0,)`, while `build_adjacency_matrix(Netlist())` is
   `np.array([]).reshape(0, 0)` with **no** dtype argument and is therefore
   `float64`. A port that tidied these into one dtype would be a behaviour
   change; `test_build_adjacency_matrix_empty_keeps_float64_shape_0_0` pins
   it.

8. **Preserved oracle quirks.** Three behaviours that read as bugs are
   reproduced rather than fixed, each with a naming test:
   `Board.rotated_90` rebuilds zones without `zone_type`, silently resetting
   a `"keepout"` zone to `"placement"`; `Board.point_in_keepout` consults
   only `mounting_holes` and never `self.keepouts` despite its docstring;
   and `Zone.bounds` is `Rect`-coerced in `__post_init__` only, so a later
   assignment stores the raw tuple (which
   `deterministic/feedback/orchestrator.py` depends on, as it writes
   inverted intermediates that a re-coercion would reject).

9. **Verbatim-transcribed algorithms.** `Netlist.find_isomorphic_groups`
   keeps the `re.match(r"^([a-zA-Z]+)", ref)` prefix rule and the
   `hashlib.md5` label digest by calling `re` and `hashlib` themselves.
   `build_adjacency_matrix` deduplicates each net's component indices before
   emitting the complete subgraph; the oracle's dedup comes from
   `list(set(...))` whose iteration order is unspecified, but the result is
   order-independent (every unordered pair contributes `+1` to both `(i,j)`
   and `(j,i)`), so the sorted dedup used here yields the identical matrix —
   asserted by MR3.

10. **Error parity.** Failure modes are compared as values, not ignored.
    `canon_call` captures exception *type name* and `str()` on both sides.
    The iterable-unpacking diagnostics CPython generates for
    `x_min, y_min, x_max, y_max = value` and `for ref, _ in pins`
    (`cannot unpack non-iterable X object`, `not enough values to unpack
    (expected N, got M)`, `too many values to unpack (expected N)`) are
    re-implemented in `unpack`/`unpack2`, because a pyo3 tuple `extract()`
    raises different text and rejects lists outright. The differential
    caught exactly this divergence before it was fixed.

11. **`LayerStackup._test_only_2layer` frame inspection.** The oracle reads
    its *caller's* filename via `sys._getframe(1)`. A `#[pymethods]`
    classmethod has no Python frame of its own, so the caller's frame is
    `sys._getframe(0)` from Rust — index shifted by one, same frame
    selected; likewise `warnings.warn(stacklevel=2)` becomes `stacklevel=1`.
    The equivalence is not asserted by inspection but *demonstrated*: the
    differential drives both sides from a synthetic frame compiled with the
    filename `/opt/production/pipeline.py` and requires the same
    `RuntimeError` text naming that file, and separately requires the same
    warning message when called from this test file.

## Documented deviations (per R1, recorded here)

1. **Submodule placement.** The pyclasses live in
   `temper_design_bundle_python.board_contracts` / `.netlist_contracts`
   rather than the extension root, because `board.py` and `netlist.py` each
   define a class named `Component`; one flat namespace would silently alias
   one over the other. Nesting also keeps each pyclass's
   `__name__`/`__qualname__` equal to the dataclass it replaces, which the
   `repr` and `unhashable type: 'X'` parity assertions depend on. Consumers
   are unaffected: they import from `temper_placer.core.board` / `.netlist`
   exactly as before.

2. **`__module__`.** Each pyclass reports
   `temper_design_bundle_python.board_contracts` where the dataclass
   reported `temper_placer.core.board`. `__name__`/`__qualname__` are
   unchanged, and no in-repo consumer reads `__module__` for these types
   (`placer/cp_sat/_loop_routing.py:68` reads `__class__.__name__` only, as
   a fallback when `ref` is absent).

3. **Not pickleable.** The pyclasses define no `__reduce__`, and the
   submodules are not in `sys.modules`. Verified 2026-08-04 that nothing
   in-repo pickles or `copy.deepcopy`s any of these types.

4. **The dataclass protocol is restored, not dropped.** An earlier draft of
   this section claimed nothing in-repo applied `dataclasses.replace` to
   these types. **That claim was wrong**, and the consumer suite disproved it:
   `deterministic/stages/apply_placements.py` rebuilds both `Component` and
   `Netlist` with `replace()`, and the migration broke it with
   `TypeError: replace() should be called on dataclass instances`. The
   original grep was scoped to lines that also mentioned a contract type by
   name, which `replace(component, ...)` does not.

   `temper_placer/core/_contract_dataclass_compat.py` now installs a genuine
   `__dataclass_fields__` on each pyclass, built from a throwaway
   `dataclasses.make_dataclass` prototype carrying the same field list and
   the same `init` flags — so the `Field` objects are real rather than faked
   around the private `_FIELD` sentinel, and `replace()`, `fields()` and
   `is_dataclass()` all behave as they did pre-migration.
   `Board._zone_map` keeps `init=False`, so `replace()` still refuses it with
   the same `ValueError`. Field-name and `init`-flag parity against the
   oracle is asserted by `test_dataclass_field_surface_matches_the_oracle` in
   both differentials.

   The methodological lesson, recorded because it generalizes to the
   remaining Phase-3 candidates: **a contract differential proves the
   contract, not the consumers.** Both gaps found in this migration
   (`dataclasses.replace`, and `board.traces` attribute injection) were
   properties of a `@dataclass` that no consumer declares and no contract
   test would think to assert. Both were caught only by running the broad
   suite against a *pre-migration baseline of the same selection* — the
   comparison, not the absolute pass count, is what made them visible, since
   ~10 unrelated environment failures were present on both sides.

5. **KTD7 overturn — the plan's keep-Python decision for the numpy/re/hashlib
   kernels is overturned by migration.** The plan's R1 wording ("every numpy
   `float32`-returning method stays in the shim as a thin deterministic
   wrapper") kept `build_adjacency_matrix` (a float32-returning method) in
   the shim, and the general "compute kernels stay Python" framing carried
   `find_isomorphic_groups` with it. Both are **migrated to Rust** — but in
   the plan's own spirit: they call `re`/`hashlib`/numpy themselves across
   the boundary (structural proof cases 7 and 9), so no third-party
   algorithm is re-implemented and the bit-parity is provable rather than
   assumed. Rationale for overturning: their consumers are hot-path compute
   (`core/community.py` calls `build_adjacency_matrix` at lines 57/119), and
   keeping them Python behind the shim would have made every array-returning
   method a Python hop while the class itself was Rust. The Rust versions
   are pinned by P6/P7/P8, MR3 (net permutation leaves the adjacency matrix
   bit-identical), the empty-path float64 `(0, 0)` dtype pin, the
   `iterations ∈ {0, 1, 2, 3}` parity pins, and the malformed-pin fuzzing.
   The R20 evidence chain is preserved because the bit-parity differential
   gates them (a mutant kernel cannot survive `(dtype, shape, tobytes())`
   comparison). The one genuinely non-deterministic kernel,
   `compute_eigenvector_centrality`, stays Python exactly as the plan's R1
   requires — R3 #2 above.

6. **Explicit `None` for a literal default collapses to the default on the
   pyclasses.** The pyo3 `Option<&Bound<PyAny>>` parameters cannot
   distinguish an *omitted* argument from an *explicitly passed* `None`
   (pyo3's `extract_argument_with_default` extracts a present `None` to the
   Rust `None` and only uses the default when the argument is absent). The
   dataclasses store what they are given, so
   `MountingHole(pos, dia, keepout_radius=None).keepout_radius` is `None`
   in the oracle but `3.0` on the pyclass; `Zone(..., net_classes=None)`
   stores `None` in the oracle but `["Signal"]` on the pyclass; and the
   literal-default fields of `Component`/`Pin`/`Net`
   (`net_class="Signal"`, `fixed=False`, `width/height=1.0`,
   `shape="rect"`, `layer="F.Cu"`, `drill=0.0`, `is_pth=False`,
   `roundrect_ratio=0.25`, `pad_rotation_deg=0.0`, `weight=1.0`,
   `max_current=0.0`, `voltage_class="LV"`) behave identically.
   **Recorded, not fixed**, per the R1 deviation rule: a pyo3 sentinel
   default *is* mechanically possible in pyo3 0.29 (defaults are per-call
   Rust expressions), but it would render `keepout_radius=...` in
   `__text_signature__` (a real observable surface, currently untested but
   part of the contract) and requires ~20 per-param sentinel identity checks
   across five classes — churn against a 105-test differential for a
   divergence with **zero in-repo callers** (verified 2026-08-04: no caller
   passes explicit `None` for any of these fields). The divergence is pinned
   explicitly instead: `test_explicit_none_literal_defaults_divergence_pinned`
   in both differentials asserts each arm's exact behavior on `{field: None}`
   inputs for the affected classes (the #712 pattern-5 precedent). A future
   caller passing explicit `None` will be caught by those pins rather than
   silently diverging. If the product authority prefers oracle parity over
   `__text_signature__` parity, the sentinel mechanism is the recorded path.

## R11 consumer-semantics catalog — re-scope record (2026-08-04)

This record re-scopes plan requirement **R11/U4** — the full enumeration of
the **69 board + 77 netlist src importers** (`grep -rl` over
`packages/temper-placer/src/` for modules importing
`core.board`/`core.netlist` at the pre-migration base; counting rule and
provenance in `docs/evidence/2026-08-04-r11-consumer-semantics-re-scope.md`)
— for this migration.

**Re-scope.** The full per-symbol enumeration of every importer's usage is
explicitly RE-SCOPED by this record to the enumerated pin-list below: the
consumer behaviors this migration's differentials pin **by name**. This is a
plan-level change; it takes effect on the product authority's concurrence,
and a fresh full enumeration remains available as a follow-up if the
authority rejects the re-scope.

**Why full enumeration is superseded.** The stacked PRs built against these
contracts — #716 (config/reference loaders, merged into this branch),
#718/#723 (further candidates) — constructed and consumed `Board`/`Netlist`
through their own differentials and reviews, exercising the consumer surface
broadly. The broad-suite baseline comparison at this pull (pre-migration
baseline vs migration, same selection, same process) found **both** escaped
regressions a full enumeration exists to catch — `dataclasses.replace` and
`board.traces` injection — which is the strongest evidence available that the
enumerated surface below, plus the comparison, covers the consumer
semantics that matter. The two regressions were properties of the
`@dataclass` protocol, not of individual call sites, which is precisely why
a call-site enumeration alone would not have caught them either.

**The enumerated pin-list — every consumer behavior the differentials pin by
name:**

| # | Consumer behavior | Pinned by (differential/PBT/MR) |
|---|---|---|
| 1 | `Net.pins` list identity — `io/_parse_nets.py:50` `nets_dict[pin.net].pins.append(...)` must land in the stored list | `test_net_pins_list_is_shared_by_identity` |
| 2 | `dataclasses.replace()` — `deterministic/stages/apply_placements.py` rebuilds `Component`/`Netlist` | `test_dataclasses_replace_works_on_the_public_contracts` (both), `test_replace_rejects_the_init_false_field_identically`, `test_dataclass_field_surface_matches_the_oracle` (both) |
| 3 | `board.traces` attribute injection — `validation/trace_analyzer.py`, `visualization/board_renderer.py` | `test_undeclared_attributes_can_be_attached_like_on_a_dataclass`, `test_mutable_contracts_accept_undeclared_attributes` |
| 4 | Duck-typed zones — `cli/__init__.py:419` assigns anonymous `type("Zone", ...)` instances | `test_board_zones_accepts_duck_typed_objects` |
| 5 | Raw-tuple `zone.bounds` assignment (no re-coercion) — `deterministic/feedback/orchestrator.py` writes inverted intermediates | `test_zone_bounds_assignment_does_not_recoerce` |
| 6 | `pin.net` mutation — `fixtures/synthetic.py` | `test_pin_is_mutable_like_the_dataclass` |
| 7 | `build_adjacency_matrix` duck-typed on `.components`/`.nets` — `core/community.py:57,119` | `test_build_adjacency_matrix_accepts_the_delegating_public_class`, `test_build_adjacency_matrix_is_bit_identical_including_dtype`, `test_build_adjacency_matrix_empty_keeps_float64_shape_0_0` |
| 8 | `LayerIndex` stays a Python `IntEnum` (int-comparison deviation, R3 #1) — `router_v6/constraints_drc_oracle.py`, `deterministic/stages/_grid_hv.py`, `net_types.rs` | `test_layer_index_stays_a_python_intenum_r3`, `test_layer_index_surface_matches_the_oracle`, `test_layer_predicate_helpers_identical` |
| 9 | Container identity on mutable fields generally — `Component.pins`, `Board.zones`, `Board.keepout_regions is Board.keepouts` | `test_component_pins_list_is_shared_by_identity`, `test_board_zones_list_is_shared_by_identity`, `test_board_keepout_regions_alias_is_the_same_list_object` |
| 10 | `net.net_class` assignment — `io/_parse_nets.py`, `Netlist.apply_net_class_mapping` | `test_net_class_is_assignable`, `test_netlist_apply_net_class_mapping_identical` |
| 11 | `build_indices` rebinds (not mutates) and rebuilds after mutation — callers mutate then re-index | `test_netlist_build_indices_rebuilds_after_mutation`, MR1/MR4, `test_netlist_explicitly_passed_indices_are_overwritten` |
| 12 | numpy surface — `polygon_array`, `get_bounds_array`, `get_relative_bounds_array`, `get_fixed_mask` dtype/bit pins for every array consumer | `test_board_polygon_array_is_bit_identical_including_dtype`, `test_board_bounds_arrays_are_bit_identical_including_dtype`, `test_netlist_bounds_array_is_bit_identical_including_dtype`, `test_netlist_fixed_mask_is_bit_identical_including_dtype`, `test_netlist_empty_arrays_keep_their_dtypes`, `test_board_has_polygon_outline_identical` |
| 13 | `Board.rotated_90` preserves the zone-type-reset oracle quirk | `test_board_rotated_90_drops_zone_type_identically` (+ the rotation MRs) |
| 14 | Frozen semantics — `Trace`/`Via`/`Rect`/`LayerStackup` reject mutation with CPython's own `FrozenInstanceError` text | `test_frozen_dataclasses_hash_and_reject_mutation_identically`, `test_frozen_contracts_reject_undeclared_attributes_identically`, `test_rect_is_frozen_identically`, `test_layer_stackup_is_frozen_identically` |
| 15 | Point queries — `contains_point`, `point_in_keepout`, `get_zone_for_point`, `get_ground_domain` | `test_board_point_queries_identical`, `test_zone_contains_point_identical`, `test_ground_domain_contains_point_identical` |
| 16 | Unpacking diagnostics on malformed pins — the `for ref, _ in pins` CPython error text for every pin-consuming path | `test_malformed_pin_tuples_fail_identically` (extended to `Netlist(...)` construction, `build_indices()`, list-valued and wrong-arity pins), `test_malformed_pin_tuples_is_non_vacuous` |
| 17 | `LayerStackup.is_plane_layer` tuple-indexing semantics — float index raises the oracle's `TypeError`, out-of-range returns `False` | `test_layer_stackup_is_plane_layer_identical` (float 1.5/2.5, out-of-range, bool cases) |
| 18 | Explicit-`None` divergence pins — the #712 pattern-5 divergence record for the literal-default fields of `MountingHole`/`Zone`/`Component`/`Pin`/`Net` | `test_explicit_none_literal_defaults_divergence_pinned` (both differentials) |
| 19 | `find_isomorphic_groups` parity for every `iterations ∈ {0, 1, 2, 3}` and the empty netlist | `test_netlist_find_isomorphic_groups_identical`, `test_netlist_find_isomorphic_groups_empty_identical`, P8 |

**Drift mechanism (R13).** With full enumeration re-scoped, the R13 drift
mechanism operates via the **per-pull scorecard convention**: every later
pull that consumes `Board`/`Netlist` (or adapts a consumer to them) records
any new consumer adaptation against this list **in its own pull** — the same
rule the migration's own consumer adaptations followed (rows 2, 3, 4, 6, 7
above were each added to the differentials by the pull that discovered
them). A pull that changes a consumer behavior without a pin lands red on
the relevant differential row. This record, not the deleted enumeration, is
the reference the next pull diffs against.

## Evidence

## Mutation campaign (anti-vacuity)

Six mutants, every one caught by the differential/PBT suites (the campaign
record from the PR body, committed here so the table does not live only in
the PR):

| # | Mutant | Caught by |
|---|--------|-----------|
| M1 | `Netlist.get_bounds_array` dtype `float32` → `float64` | 2 failed — `test_netlist_bounds_array_is_bit_identical_including_dtype`, P6 |
| M2 | `Rect.from_xyxy` stops coercing to `float` | 17 failed — the whole type-preservation cluster |
| M3 | `Zone.width` computes `bounds[0] - bounds[2]` (sign flip) | 4 failed — geometry properties + `Zone` repr parity |
| M4 | `Net.pins` stores a **copy**, losing caller identity | 1 failed — `test_net_pins_list_is_shared_by_identity` |
| M5 | `Board.__repr__` omits the `init=False` `_zone_map` field | 5 failed — `Board` repr/aggregate parity |
| M6 | empty `build_adjacency_matrix` uses `float32` instead of `float64` | 2 failed — `test_build_adjacency_matrix_empty_keeps_float64_shape_0_0` |

Clean build immediately after the campaign: 214 passed (the pre-review
differential count; the review-pin additions below raise it).

Review-pass pins (2026-08-04) added to the differential/PBT surface:
- `test_layer_stackup_is_plane_layer_identical` gained float-index rows
  (1.5, 2.5) and `True`, pinning the tuple-indexing error text: a float index
  passes the oracle's `0 <= idx < len` guard and reaches
  `self.layers[1.5]`, which raises `TypeError: tuple indices must be
  integers or slices, not float` — the pyclass now tuple-indexes through
  CPython's own `get_item` instead of a `usize` extract (board_contracts.rs
  `is_plane_layer`), and out-of-range ints still return `False` on both arms
  (the guard fails first; no `IndexError`).
- `test_malformed_pin_tuples_fail_identically` was extended from
  `Net.get_component_refs` alone to also drive `Netlist(...)` construction
  and `netlist.build_indices()` re-runs, with list-valued and wrong-arity
  pins added to the generator. `compute_indices` (netlist_contracts.rs) now
  uses the shared `unpack2` helper instead of a raw pyo3 2-tuple `extract()`
  (which rejects lists outright and raises different text).
- `test_explicit_none_literal_defaults_divergence_pinned` (both
  differentials) pins the explicit-`None`-for-literal-default collapse
  (documented deviation 6): each arm's exact behavior on `{field: None}`.

- Differential (R1a/R1f, TDD red→green): 214 runtime assertions at the
  original pull across
  `packages/temper-placer/tests/core/test_board_rust_differential.py`
  (oracle `_board_py_oracle.py`, commit `5a17025b1`) and
  `test_netlist_rust_differential.py` (oracle `_netlist_py_oracle.py`,
  commit `e799183c4`); the 2026-08-04 review-pass pins above raise the
  runtime count. RED first: both files failed to collect
  (`AttributeError: module 'temper_design_bundle_python' has no attribute
  'netlist_contracts'`) before the pyclasses existed.
- Comparison convention: `tests/core/_contract_canon.py` carries each leaf's
  concrete `type` and compares floats as `float.hex()` — never a tolerance —
  and numpy arrays as `(dtype, shape, tobytes())`. `canon_call` compares
  raised exceptions by type name and message, so error parity is asserted
  alongside value parity.
- PBT (R1c): 9 properties per module — `test_board_pbt.py` P1–P9,
  `test_netlist_pbt.py` P1–P9 — each stated against the pinned oracle, and
  each whose generator could degenerate paired with a
  `test_*_is_non_vacuous` companion proving the interesting region is
  actually reached (both `mask_expansion` values; all four `validate()`
  error classes; both `polygon_array` outcomes; both `Rect.__init__`
  outcomes; a real `int` in the coordinate corpus; last-wins zone-name
  collisions; a self-referencing net that would put a `1` on the adjacency
  diagonal if the dedup were dropped). Error-path parity under fuzzing:
  `test_malformed_pin_tuples_fail_identically` drives malformed
  (list-valued, wrong-arity, non-iterable) pins through all three unpack
  sites (`Net.get_component_refs`, `Netlist(...)` construction,
  `build_indices()` re-runs) with type+message parity, vacuity-anchored by
  `test_malformed_pin_tuples_is_non_vacuous`.
- Metamorphic (R1d): 4 relations per module. Board — MR1 (repeated rotation,
  including the degenerate `Rect` raise compared as a value), MR2 (four
  rotations restore the envelope, one transposes it), MR3
  (`from_xywh`/`from_xyxy` describe the same rectangle), MR4
  (`build_indices` idempotent; zone order decides name collisions). Netlist
  — MR1 (`build_indices` idempotent), MR2 (component permutation permutes
  the bounds-array rows), MR3 (net permutation leaves the adjacency matrix
  bit-identical), MR4 (appending one component grows the index by exactly
  one and leaves the rest fixed).
- Performance A/B (R1b): contract construction with no compute kernel, so
  per R2 this is the *no-regression-beyond-noise* arm, not a speedup claim.
- R1g: no `unwrap`/`expect` outside tests (the crate denies both via
  `[lints.clippy]`); every container field is stored and returned by
  borrow/handle rather than copied; `build_indices` reads all Python state
  before opening its `borrow_mut`, so re-entrant user code cannot observe a
  locked object. Panics at the pyo3 boundary are converted by pyo3 0.29's
  generated trampolines (`catch_unwind` in the `#[pymethods]` expansion) —
  the same mechanism relied on by every landed migration in this crate.
- R1h: **N/A — these modules hold no state machine.** They are data
  contracts; the only mutable state is the caller's own field values and the
  three derived index dicts, whose rebuild is asserted idempotent (MR1/MR4).

---

# Config / reference loaders — Verification

The config/reference loaders (`src/config_loader.rs`, `src/reference_loader.rs`
in this crate; `src/footprint_library.rs`, `src/reference_aliases.rs` in
`temper-io-types`) are Wave 4 **Phase 3, candidate 5** (plan
`docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`), ported from
`temper_placer/io/config_loader.py` (967 LOC), `io/reference_loader.py` (405),
`io/footprint_library.py` (213) and `io/reference_aliases.py` (92). All four
Python modules are now delegation shims (config_loader and reference_loader
keep their orchestration Python where the parse engine / numpy boundary is
unmigrated; footprint_library and reference_aliases are pure re-exports).

## Home-crate decision (Q3)

The candidate splits across the two seeded crates, on dependency grounds:

- **`temper-design-bundle`** owns `config_loader.rs` and `reference_loader.rs`
  because the config loader constructs this crate's own contract pyclasses
  (`Zone`, `GroundDomain`, `Board`, `LayerStackup`, `NetClassification`) and
  calls `NetClassification.from_yaml_config` (already Rust here); a
  dependency from `temper-io-types` onto this crate would have been the only
  one of its kind.
- **`temper-io-types`** owns `footprint_library.rs` and `reference_aliases.rs`
  because `FootprintSpec` already lived there (`footprint_spec.rs`, the pure
  data holder); the loader reuses it, and neither module touches the
  contract pyclasses.

## The pydantic boundary (the candidate-5 crux)

**pydantic is not reimplemented in Rust.** Two of the three authorities in
the load chain stay on the Python side and are called back across the
boundary, exactly like `design_rules.rs`'s Python call-backs:

1. **PyYAML** (`yaml.safe_load`) — YAML 1.1 vs serde_yaml's 1.2 disagree on
   `on`/`off`, `012`, `1_000`. Re-tokenising in Rust would change behaviour
   while the differential on shipped fixtures stays green; the differential
   pins a YAML-1.1 discriminator (`thermal_pad: on` → `True`) so the choice
   is load-bearing, and mutant M2 (a BaseLoader no-typing parse) was caught.
2. **pydantic** (`PlacementConstraints.model_validate`) — the final authority
   over coercion, constraint validation and the `ValidationError` text. A
   second, drifting copy of the schema in Rust is exactly what this
   candidate refuses to build.

Everything downstream of the YAML parse — field mapping, default evaluation
order, coercion *order*, dict iteration order, the eager typed-construction
error timing (a `ClearanceRule(...)` inside the transform raises *before*
`model_validate`, unwrapped by `load_constraints`), and the post-validate
passes (`_emit_keepout_constraints`, `_build_net_classification`,
`_validate_current_capacity`) — is Rust, with typed leaves constructed by
calling the Python classes at the same points the oracle does (pydantic
models from `temper_placer._constraint_types`, `NetGraph`/`SubNetEdge` from
`core.net_graph`, PCL constraints from `temper_placer.pcl`,
`estimate_current_from_net_class` from `core.ipc2221`), so error timing and
error text are the oracle's by construction. Arithmetic (`bounds_ratio`
scaling, fixed-position floats) goes through Python's own operators
(`PyAnyMethods::mul` etc.), never Rust `f64`, so `int`-vs-`float` outcomes
are CPython's (board-contracts case-6 lesson). `round()` in
`reference_loader.rs` is CPython's own `round()` called back (banker's
rounding on the exact binary value — the candidate-6 trap; mutant M8, a
`f64::round` half-away-from-zero port, was caught by a `0.0625` exact-tie
density discriminator).

## R3 boundary decision (named blocker)

`reference_loader.py`'s *load* path — `load_reference_pcb` (calls the KiCad
parse engine, candidate 3, built in parallel), `filter_components` (numpy
fancy indexing + `ParseResult` construction) and
`netlist_to_placement_state` (numpy `PlacementState`, a Phase 4/5 surface) —
**stays Python** until those surfaces land; the two pure kernels
(`compute_design_stats`, `infer_quality_config`) are Rust and the shim calls
them. This is not a deferral: the kernels are pure over the candidate-1
`Netlist`/`Net`/`Board` pyclasses, so migrating them now is sound, and the
entangled orchestration names its blockers (parse engine, numpy
`PlacementState`).

## Induction applicability

**Mathematical induction is not applicable to these modules.** No loader
function is recursive, and none iterates over a dimension whose correctness
depends on a size parameter: `preprocess_config` is a fixed section-by-section
dict transform (each section's correctness is local), `from_yaml_string` /
`load_reference_alias_manifest` validate per-entry with per-entry
independence, and the stats/quality kernels fold over caller-provided
collections with per-element independence (asserted by the permutation MRs).
Per the plan's R1e, a **structural proof** is recorded instead:

**Claim (bit-identical parity).** For every migrated symbol, the Rust
behaviour is bit-identical to the pinned pre-migration Python
implementations (`tests/io/_config_loader_py_oracle.py` etc., commit
79ab9bd0e).

*Proof by structural cases.* (1) **Field mapping/defaults** — every `.get(key,
default)` call is transcribed with the oracle's exact default and evaluation
order, and every typed leaf is constructed by calling the Python class at the
same point, so construction errors raise with the oracle's timing and text.
(2) **Coercions** — `float()`/`bool()`/`str()`/`int()`/`tuple()`/`set()` are
CPython's own constructors called back. (3) **Iteration order** — dict
iterations go through `items()` (insertion order), asserted by MR1; a
HashMap-based port would scramble it. (4) **Truthiness-`or`** — the
differential-pair and `via_template` fallbacks preserve `x or y` semantics
(P5 pins the falsy-primary cases). (5) **Numeric leaves** — all arithmetic
through Python operators; `round()` through CPython; `{:.1f}`-style messages
format identically (both languages round decimal digits half-to-even).
(6) **Error strings** — every `ValueError`/`KeyError`/`FileNotFoundError`
message is transcribed byte-identically and asserted by the differential's
`canon_call` error parity. (7) **Type preservation** — `FootprintSpec`
stores the caller's own objects (`Py<PyAny>`), so `bounds: [2, 1]` stays
`int`; the pydantic `model_validate` authority then coerces exactly as it
always did.

## Mutation campaign (anti-vacuity)

Ten mutants, every one ultimately caught by the differential/PBT suites;
three survived their first run and were closed by adding discriminating
fixtures (the guide's survivable-mutant pattern):

| # | Mutant | Caught by | Notes |
|---|--------|-----------|-------|
| M1 | footprint bounds `len == 2` check dropped | invalid-bounds error parity | |
| M2 | `yaml.safe_load` → `yaml.BaseLoader` (no scalar typing) | 7 failures incl. the YAML-1.1 `on` discriminator | proves the PyYAML call-back is load-bearing |
| M3 | self-alias check dropped | `test_rejects_self_alias` | |
| M4 | `str.strip` → Rust `str::trim` | **strip is load-bearing** — a trim-based port would diverge on escape-decoded C0 controls | Python `str.strip` strips U+001C-U+001F (part of its Unicode whitespace set); Rust `str::trim`/`char::is_whitespace` does not (category Cc, not White_Space). PyYAML DECODES the double-quoted escape `"\x1c"` into U+001C — the Reader validates the raw input stream, not decoded escapes — so the divergence IS reachable. The `"\x1c"`-escaped fixture in `test_reference_aliases_rust_differential.py::test_escape_decoded_control_char_name_rejected` pins the call-back: the oracle rejects the name as empty, and the shim reaches the same verdict through the KEPT Python `str.strip` call (reference_aliases.rs:182); a trim-based port would accept it (asserted via the Rust unit test `rust_trim_keeps_u001c_where_python_strip_removes_it`). |
| M5 | `_NAME_MAP` `zone_membership` alias dropped | P3 / P1 | |
| M6 | `allow_neckdown` default flipped | production-fixture differential | |
| M7 | differential-pair key-existence fallback | rewritten P5 | the exploration **exposed a real bug**: the initial Rust had key-existence (the truthiness-or fix had silently not applied) and P5's first draft was vacuous (no negative net in any case) — both fixed. The fix scope is the FULL truthiness-or chain: the pos/neg polarity fallbacks (`positive_net or net_pos`) **and** the spacing/impedance fallbacks (`separation_mm or spacing_mm or 0.2`, `target_impedance_ohm or impedance_ohm`) — key-existence on the latter fed `0` into pydantic's `gt=0` spacing field (raise) or `0.0` into impedance where the oracle yields `None`. RED fixtures: `separation_mm: 0`, `spacing_mm: 0`, `target_impedance_ohm: 0`, `impedance_ohm: 0`, each alone and alongside a live fallback key (commit 3b387e7cc, 9 failed) |
| M8 | CPython `round()` → `f64::round` | `0.0625` exact-tie density discriminator | survived v1 (whole-number fixtures); round-half-even gives 0.062, f64::round 0.063 |
| M9 | `loops[:3]` cap dropped | loop-cap test / P5 | |
| M10 | `LossConfig.enabled` default flipped | dict-form-losses discriminator | survived v1 (the `loss_weights` path goes through the float branch and cannot see it) |

## Recorded risks (per R1, documented here)

Two review-flagged risks are recorded, not fixed — both are unreachable from
the shipped corpus and neither currently diverges:

1. **Triple-source RJC table drift.** `infer_rjc` carries a Rust copy of the
   package table (`RJC_PACKAGE_LOOKUP` / `DEFAULT_RJC` in `config_loader.rs`,
   lines ~192/205) while the shim keeps the legacy module constants
   (`_RJC_PACKAGE_LOOKUP` / `_DEFAULT_RJC` in `io/config_loader.py`) for
   import-surface stability — and the same table exists a THIRD time in
   `temper_placer/_constraint_types/thermal.py` (`_RJC_PACKAGE_LOOKUP` /
   `_DEFAULT_RJC`, the thermal-constraint module's own copy, predating the
   migration). All three copies now agree, each carries a cross-linking
   "mirrors ..." comment naming the other two, and the differential's
   `test_infer_rjc_matches_oracle` exercises the Rust table against the
   oracle's own constant-driven `infer_rjc` — so a drift in the Rust table
   would be caught, but a simultaneous edit of two or three of the tables (or
   a drift in the shim/thermal constants, which the differential does not
   read) would not be. Nothing enforces future identity; a follow-up could
   derive one table from the other or pin all three in a single shared
   fixture.
2. **Non-dict `board` section error-family divergence risk.** A non-dict
   `board` value reaches the `.get` probe through different mechanisms on
   the two arms (oracle: Python attribute access `board.get(...)`; Rust:
   `call_method("get", ...)`). On every reachable probe (`int`, `float`,
   `bool`, `str`, `list`, `None`) both arms raise `AttributeError: '<T>'
   object has no attribute 'get'` with identical text, so the shipped
   behavior agrees; the *family* could split only for a mapping-lite type
   whose `.get` resolves via `__getattr__` (or shadows differently), which
   no YAML document can produce. Untested by design — unreachable from the
   shipped corpus (every production config has a dict `board` section).

## Evidence

- Differential (R1a/R1f, TDD red→green): 56 assertions across
  `tests/io/test_{config_loader,reference_loader,footprint_library,reference_aliases}_rust_differential.py`
  (oracles `_*_py_oracle.py`, commit 79ab9bd0e). RED first: all four failed
  to collect (`AttributeError: module 'temper_io_types' has no attribute
  'FootprintLibrary'`) before the Rust landed. Floats via `float.hex()`,
  concrete leaf types in comparison keys, error type+message parity via
  `canon_call`, numpy arrays as `(dtype, shape, tobytes())`.
- PBT (R1c): 6+5+6+6 = 23 properties across the four `test_*_pbt.py` files,
  each parity- or invariant-stated against the pinned oracle and vacuity-
  guarded (int-bounds type preservation, empty-input semantics, the
  falsy-primary differential-pair cases, the `0.0625` tie, the loop cap).
- Metamorphic (R1d): 3 relations per module (16 total): insertion-order
  preservation, add-replace idempotence, get-default (footprint);
  available-set independence, set order, namespace isolation (aliases);
  insertion order, unknown-section independence, losses-vs-loss-weights
  precedence (config); permutation, append, additive area (reference).
- Performance A/B (R1b): `benchmarks/perf_ab.py` registers
  `config-loader/preprocess_config` and `footprint-library/from_yaml_string`
  — pure-delegation arms (both sides call the same Python constructors), so
  the honest claim is no-regression-beyond-noise, and no speedup is claimed
  (measured local ratios 1.26 / 0.85 — marshalling-dominated, and baselines
  are captured on CI per the harness docs).
- Consumer suites: all 371 `tests/io/` tests pass (including the pre-existing
  `test_footprint_library.py`, `test_reference_aliases.py`,
  `test_config_validation.py`, `test_escape_clearance.py`,
  `test_net_topology_config.py`, `test_integration.py`); the broad suite shows
  no regression — every one of the 16 failures present is pre-existing at the
  base commit (verified in a scratch worktree: physics-provenance script
  tests, closure/router runs, mfem binary, kicad-cli courtyard counts).
- R1g: no `unwrap`/`expect` outside tests (both crates deny them via
  `[lints.clippy]`); container fields are stored/returned by handle
  (`Py<PyAny>`) not copied; every Python call-back is a `PyResult` and panics
  at the pyo3 boundary are converted by pyo3 0.29's generated trampolines
  (`catch_unwind` in the `#[pymethods]`/`#[pyfunction]` expansion).
- R1h: **N/A — the loaders are not physics-gated.** They move numbers
  (bounds, clearances, current ratings) without gating on a physics quantity;
  the R24 discipline (soundness proof, BMC, post-solve audit) applies to
  CP-SAT constraints, not to config parsing.
- Type-check: stubs updated in `temper_design_bundle_python/__init__.pyi`;
  the `io/config_loader.py` allowlist entry shrank 2 → 0 errors.

---

# Parse engine — Verification

The parse engine (`src/parse_engine.rs`) is the Wave 4 Phase 3 candidate 3
migration (plan `docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`):
the KiCad `.kicad_pcb` read engine ported from
`temper_placer/io/{kicad_parser,_parse_board,_parse_modules,_parse_nets,
_parse_tracks,_parse_zones,_kicad_types,kicad_metadata}.py` (~1,983 LOC at the
plan's measurement). kiutils leaves the product boundary (parent R4): the
Python modules are now delegation shims, and the engine parses the raw text
itself. The home crate is **temper-design-bundle** (not temper-io-types):
the engine constructs the board/netlist contract pyclasses from candidate 1
and reuses the crate's sexpr/contract machinery; a temper-io-types home would
have required a new cross-crate dependency purely to host the engine.

## Candidate scorecard (why parse-engine, and where the boundary is drawn)

Candidate 3 is the parse engine as the parent plan names it. The engine
covers: the kiutils-exact tokenizer, the raw board model (footprints, pads,
graphic items, zones, nets, segments/vias/arcs, stackup, layers, general),
and the extraction ports producing the contract pyclasses
(`ParseResult`/`TraceData`/`PadData`/`ViaData` moved to Rust pyclasses in
this crate; `DrillDefinition` and `Position` pyclasses reproduce kiutils'
dataclass shapes so through-hole `Pin.drill` values compare bit-identically).
Three boundaries stay Python, each with a named blocker:

- **`_extract_courtyards` (GEOS).** The courtyard polygons use shapely/GEOS
  (`Point.buffer`/`MultiPoint.convex_hull`/`unary_union`), which is not
  reimplementable in Rust bit-exactly (the phase guide records 169/169
  mismatches for a simpler geometry op). The engine produces the raw
  courtyard inputs; the shim runs the *identical* shapely code on them, so
  the GEOS outputs are equal by construction once the raw inputs are proven
  bit-identical (they are — the metadata differential asserts the full
  `KiCadMetadata`).
- **`_extract_stackup` + `_is_plane_required_net`.** The v6-only stackup
  assembly targets the Python `router_v6.stage0_data` dataclasses and reads
  the Python-side netclass SSOT; the raw stackup/zones come from the Rust
  engine (`extract_stackup_raw`).
- **`_apply_safety_classifications` + `_extract_design_rules` assembly.**
  Classification is a pure function over the contract pyclasses; the
  design-rules assembly targets the Python `NetClassRules` dataclass. The
  text kernel (`extract_net_classes`) is Rust. Both arms apply the identical
  Python to identical inputs, so the differential's claim is unaffected.
  `_get_footprint_reference` is likewise retained in `_parse_modules.py`
  (kiutils-free attribute reading) for the Phase-4 consumer
  `validation/placement_roundtrip.py`, which still re-parses written boards
  with kiutils.

`parse_kicad_schematic` was RETIRED in this candidate (plan R8: a `pass`
stub returning an empty netlist; its kiutils `Schematic` import had to leave
with the R4 gate; the sole consumer test was updated in this PR).

## Tokenizer correctness (the float-parse crux)

kiutils 1.4.8 tokenizes with a hand-written regex whose grammar the engine
reproduces exactly (see the module docs): decimal tokens are numeric only
when followed by a space or `)`, parse via `float()`, and become **int** when
integral (`3.0` -> `3`); integer tokens stay int; everything else is a
string. The corpus was enumerated before the engine was claimed: 39,753
distinct numeric tokens, all plain decimals/ints (no scientific notation),
so Rust `str::parse::<f64>()` and Python `float()` agree bit-for-bit (both
IEEE round-to-nearest) — the plan's Q1 float-parse assumption, verified.
The int-vs-float distinction is carried through the raw model (`Num`) and
into the output (e.g. `Board.origin` is `(int, int)` on integer boards,
exactly as the oracle produces).

## Gate set

- **R1a — behavioural A/B.** `tests/io/test_parse_engine_rust_differential.py`
  pins bit-identical `ParseResult`/`KiCadMetadata`/`DesignRules`/`StackupInfo`
  parity against the verbatim oracle package
  (`tests/io/_parse_engine_py_oracle/`, commit 79ab9bd0e) on the five-board
  corpus plus `pcb/temper.kicad_pcb`, both `normalize` values. Floats compare
  via `float.hex()`; every non-float leaf carries its concrete type in the
  comparison key (int-vs-float cannot hide); dicts compare key-sorted, lists
  in order. 42 corpus assertions + 11 discriminating fixtures (each RED
  first against both arms, closing the review findings): the M8 net-0 trace,
  empty-Reference property (dropped), no-libId footprint (both raise),
  nameless pad/board `(net N)` (both raise), via without `(layers ...)`
  (stays `()`), drill-offset angle + unlocked, `(track_width 0)` net class,
  the tokenizer-conformance matrix (caret/adjacent-quotes/backslash-quote/
  `+5`/CRLF vs `kiutils.utils.sexpr.parse_sexp`), unnumbered-pad courtyard,
  truncated position (both raise), oval drill without width (both raise).
- **R1b — performance A/B.** `benchmarks/perf_ab.py` gains the
  `("parse-engine", "parse_kicad_pcb")` benchmark: both arms run in one
  process on `pcb/temper.kicad_pcb`, outputs repr-asserted equal, ratio
  gated. I/O-shaped surface → the *no-regression-beyond-noise* arm, no
  speedup claim. Locally measured ratio 0.050 (informational; baselines are
  captured on CI and the harness treats a NEW benchmark as baseline-free).
- **R1c — properties.** `tests/io/test_parse_engine_pbt.py` P1–P7 over the
  corpus: refs are non-empty and never `REF**` (P1; uniqueness is not an
  invariant — the piantor corpus carries duplicate mounting-hole refs, and
  the oracle reproduces them); nets have >= 2 pins and no empty name (P2);
  pads reference known components (P3); bounds respect the 0.5 mm floor
  (P4); warnings deterministic (P5); zone bounds enclose the polygon (P6);
  board extents equal an independently regex-re-derived Edge.Cuts bbox (P7).
- **R1d — metamorphic relations.** M1 normalization-shift covariance (bounded
  at 8 ulp with the rationale stated; >90% bit-exact measured), M2
  whitespace/formatting invariance, M3 net-renaming covariance (connectivity
  preserved), M4 footprint-removal covariance for `extract_footprint_positions`.
- **R1e — structural proof.** The engine's recursive structure is the
  tokenizer (mutual recursion between the token scanner and the list
  builder) and the tree walkers (footprint/pad/zone/stackup recursions).
  The induction invariant is: *the raw model is a faithful projection of the
  kiutils object graph* — each walker is a direct transcription of the
  corresponding kiutils `from_sexpr`, and the differential is the induction
  step over the corpus (every corpus item class is exercised). Mathematical
  induction over a size parameter is not applicable: the walkers are
  single-pass transcriptions with no size-dependent invariant; the
  differential over the six boards (including the 169-footprint, 96-zone,
  2,338-segment production board) is the strongest applicable structural
  argument, and the extraction ports are transcription-verified line-by-line
  against the pinned oracle in the differential's canon keys.
- **R1f — TDD.** The differential and PBT suites were written first (RED:
  failed to collect against the missing `parse_engine` module), then the
  engine, then the shims; the suites went green after the engine landed.
- **R1g — Rust practice.** No `unwrap`/`expect` outside tests (crate denies
  both via `[lints.clippy]`, CI runs `-D warnings` on all targets); the
  pyclass fields are stored and returned by borrow/handle; panics at the
  pyo3 boundary are converted by pyo3 0.29's generated trampolines
  (catch_unwind in the `#[pyfunction]`/`#[pymethods]` expansions), the same
  mechanism every landed migration in this crate relies on.
- **R1h — N/A.** The parse engine is not physics-gated: it performs no
  physics computation and gates on no physics quantity, so the R24
  discipline (Chebyshev soundness proof, BMC-exhaustive validation,
  post-solve audit) does not apply.

## R2 — `parse_kicad_pcb_v6` wrapper parity (claim scope)

The plan's R2 requires the v6 wrapper re-pointed over the migrated engine
"with bit-identical `ParsedPCB` parity". This PR pins every leaf of the v6
assembly individually against the pinned oracle — `parse_kicad_pcb`,
`_extract_design_rules`, `_extract_stackup`, `extract_kicad_metadata`
(R1a) — and the assembled result is covered *by construction*: the wrapper
(`io/kicad_parser.py::parse_kicad_pcb_v6`) is line-identical to the oracle
modulo the two verified-dead kiutils branches and the equivalent stackup
source noted above. What is **not** present is a direct end-to-end
differential of oracle-v6 vs shim-v6 `ParsedPCB` objects on a real board,
and the stackup differential skips the three non-stackup corpus boards
(`temper`, `minimal`, `pcb`). The R2 claim is therefore satisfied by
leaf-parity + the consumer suites — 2,923 tests collected across
`tests/router_v6/` and `tests/validation/` exercise the v6 path end-to-end
— not by that direct differential. A direct oracle-v6 vs shim-v6
`ParsedPCB` differential on the stackup-carrying corpus boards (`rp2040`,
`bitaxe`, `piantor`) remains a possible follow-up.

## Anti-vacuity (mutation campaign)

Eight mutations, each applied to the Rust source, rebuilt, and confirmed to
fail the differential, then reverted (recorded in the PR description):

| # | Mutation | Caught by |
|---|----------|-----------|
| M1 | `py_round` → `f64::round` (rot_idx half-to-even loss) | 3 differential failures (rp2040 non-90° parts) |
| M2 | integral decimal tokens stay floats | 5 failures (int-typed pad sizes) |
| M3 | zone warning drops `'Unnamed'` fallback | 6 failures |
| M4 | empty-string nets not filtered | 2 failures (temper `''` net) |
| M5 | pin positions skip pad-centroid offset | 10 failures |
| M6 | zone singular `(layer ...)` token dropped | 7 failures (rp2040) |
| M7 | `gr_poly` `pts` not parsed | 3 failures (production board origin) |
| M8 | net-0 traces treated as named | corpus has no net-0 traces → **survived**; closed with a discriminating net-0 fixture in the differential (now fails) |

M8 is the second surviving-mutant close in the program's history: the corpus
cannot exercise a net-0 segment (none exist on any of the six boards), so a
discriminating synthetic fixture was added rather than lowering the claim.

The adversarial review added three more surviving mutants, each closed with a
discriminating fixture the same way (the corpus cannot reach them):

| # | Mutation | Closed by |
|---|----------|-----------|
| M9 | empty-Reference footprints emitted as phantom components | `test_empty_ref_property_footprint_dropped` + `test_no_libid_footprint_raises` (empty-reference property, no-libId footprint) |
| M10 | nameless `(net N)` pad/board tokens fail open (pin.net="") | `test_nameless_pad_net_raises` + `test_nameless_board_net_raises` (both arms raise) |
| M11 | via without `(layers ...)` defaulted to ("F.Cu","B.Cu") (dead oracle branch) | `test_via_without_layers_stays_empty` |
| M12 | `(track_width 0)` net class kept 0.0 (oracle's `or` is truthiness) | `test_track_width_zero_net_class_parity` |

Plus the tokenizer-conformance matrix (`test_tokenizer_kiutils_exact`) pins
the "kiutils-exact" tokenizer claim on adversarial strings the corpus cannot
contain (caret, adjacent quotes, backslash-quote runs, `+5`, CRLF,
unterminated strings), and the drill-offset / courtyard-unnumbered-pad /
truncated-position / oval-drill fixtures pin the remaining review findings.

## Documented deviations (per R1, recorded here)

- Integers outside i64 range in integral decimal tokens stay floats (Python
  ints are unbounded). Not exercised by the corpus (max ~1e10); the range
  guard is written with `i64::MIN/MAX as f64` — a `2i64.pow(63)` literal
  overflows to i64::MIN in release and silently always-falses the branch
  (this was found by the mutation campaign's build before the differential
  could, and is pinned by a unit test).
- `parse_kicad_schematic` retired (plan R8), `io/__init__.py` and
  `tests/io/test_integration.py` updated in this PR.
- The perf A/B parity assertion uses `repr()` equality rather than `==`
  because pyo3's `__eq__` NotImplemented propagation makes `rust == oracle`
  unreliable across the pyclass/dataclass boundary for identical values
  (repr is exact; both arms render the same dataclass shape).
- `_extract_stackup`'s shim signature adds a `pcb_content` keyword (the v6
  wrapper passes the content it already reads); `_extract_design_rules`
  drops the kiutils board argument usage (accepted for compatibility).
- **`Position` pyclass kwargs are lowercase (`x`/`y`) while kiutils' field
  names are `X`/`Y`** — the .pyi pins the lowercase form deliberately (no
  in-repo consumer constructs `Position` directly; the engine constructs it
  internally, and the attribute/repr surface stays `X`/`Y` for parity).
- **Non-string position coordinates fail open in Rust, fail later in the
  oracle.** A position token whose x/y are non-numeric (e.g. `(at 5^0 50)`,
  tokenized kiutils-exactly as the bare string `"5"`, int `0`, int `50`)
  is carried through by kiutils' `Position.from_sexpr` and only crashes when
  a downstream `float()` hits it; the Rust `parse_pos` keeps the walker's
  (0,0) default instead of propagating the string. Making x/y type-preserving
  would ripple through every position consumer for a token class the corpus
  never contains — recorded, not fixed. The tokenizer itself is pinned exact
  by `test_tokenizer_kiutils_exact`.
- **Non-string Reference property values** (e.g. `(property "Reference" 42)`):
  the oracle raises `AttributeError` on `ref.startswith(...)`; Rust stringifies
  the value and emits the component. Property values are flattened to strings
  in the raw model; type-preserving property values would change every
  property consumer. Recorded, not fixed.
- **Numeric / list libIds**: a numeric `(footprint 5 ...)` libId is a bare
  int in kiutils and raises AttributeError only when `_get_footprint_reference`
  reaches the entryName branch (a Reference property short-circuits before
  it); the Rust stringifies it. A LIST libId (no libId token at all) is the
  one case the engine DOES fail closed on (both arms raise — the oracle's
  entryName is the raw list, `AttributeError`; the engine's `parse_footprint`
  records a parse error) — pinned by `test_no_libid_footprint_raises`.
- **gr_arc `mid` default**: when an arc's outline excludes `(0,0)`, the
  Rust `mid` defaults to (0,0) while the oracle keeps kiutils' default
  `Position()` — the divergence only exists for arcs whose start/end bound
  the box without the origin, and the bounds extraction reads `mid` only
  when it is finite. Recorded, not fixed.
- **`(general (thickness 0))`**: the pre-migration stackup fallback used a
  truthiness check (`and ki_board.general.thickness`), so thickness 0 fell
  through to the 1.6/0.8 default; the shim's `is not None` check keeps 0.0.
  The differential's stackup parity cannot discriminate (no corpus file has
  `(thickness 0)`). Recorded, not fixed.
- **kiutils-version drift**: the oracle is frozen at kiutils 1.4.8; the
  differential cannot detect upstream tokenizer/`from_sexpr` changes.
- **M1's 8-ulp bound is engine self-covariance**: it compares the Rust
  engine against itself under normalize on/off, so a shift-invariant error
  (both arms shifted identically) passes; the differential against the
  pinned oracle is the only guard for that class, and it is corpus-bounded
  as the review findings show.
- **Stackup/design-rules differential skips corpus files without the
  surface**: `STACKUP` in the differential is `{rp2040, bitaxe, piantor}` —
  the `temper`/`minimal`/`pcb` corpus files carry no declared stackup and
  are skipped for the stackup-parity assertion (design-rules parity runs on
  all six; the v6 fallback path is exercised by the restored plane/mixed
  assertions in `tests/router_v6/test_stackup_parsing.py`).

---

# YAML loaders (netclass + loop) — Verification

The YAML loaders (`src/loaders.rs`) are the FIRST Wave 4 Phase 3 "formats/IO"
migration — candidate 2 of
`docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`, the phase's
designated opportunistic first pull. Ported from
`temper_placer/io/netclass_loader.py` (83 LOC) and
`temper_placer/io/loop_loader.py` (319 LOC); both Python modules are now
pure-delegation re-exports of the `temper_design_bundle_python` symbols.

## Candidate scorecard (why the loaders, and why they are candidate 2)

| Candidate | LOC | Risk | Dependency | Verdict |
|-----------|-----|------|------------|---------|
| `io/netclass_loader.py` + `io/loop_loader.py` | 402 | Low | none — target contracts (`DesignRules`, `Loop`/`LoopCollection`) landed as pyclasses in Phase 2 | **SELECTED** (plan candidate 2) |
| `core/board.py` / `core/netlist.py` (candidate 1) | 1,243 | High | is itself the parse-chain spine | Deferred to its own pull — the loaders are explicitly independent of it |
| `io/kicad_parser.py` + `_parse_*` (candidate 3) | 1,983 | High | depends on candidate 1 | Not pulled |
| `io/config_loader.py` + reference loaders (candidate 5) | 1,677 | Medium | pydantic + `_constraint_types`; constructs `Board`/`NetGraph` | Not pulled — depends on candidate 1 |

The plan's own dependency rationale is the selection argument: candidates 2
and 6 are the only Phase-3 candidates independent of the parse chain, and
candidate 2's parity oracle (the shipped `configs/netclass_rules.yaml` and
`configs/templates/loops/*.yaml`) already exists in-repo.

## Migration boundary (what moved, and what deliberately did not)

Two third-party/stdlib surfaces are called back across the pyo3 boundary
rather than reimplemented, and the whole save path stays Python-side. Each
is a correctness decision with a named divergence that reimplementation
would have introduced:

| Kept | Why keeping it is the correct call |
|------|------------------------------------|
| `yaml.safe_load` (the tokenizer) | PyYAML implements YAML **1.1**, `serde_yaml` implements YAML **1.2**. They disagree on inputs these files can contain: `on`/`off`/`yes` are booleans under 1.1 and strings under 1.2; `012` is octal `10` under 1.1 and decimal `12` under 1.2; `1_000` is the integer 1000 under 1.1 and a string under 1.2. Re-tokenizing would have *changed behaviour* while the differential on the shipped fixtures stayed green. Pinned by `test_load_loop_template_yaml_11_booleans_parity`, which asserts the 1.1 resolution is in force so the test cannot pass vacuously. |
| `pathlib.Path.glob` + `sorted` | `PurePath` ordering and glob pattern semantics (hidden files, `**`, character classes) are intricate and version-sensitive; delegating makes `load_loop_collection`'s traversal order exact by construction. Pinned by `test_load_loop_collection_ordering_parity` / `..._pattern_parity`. |
| `save_loop_to_yaml` (the whole save path, including `yaml.dump`) | Per KTD7 of the first-pulls plan (U3), the save path is **not part of the loaders' migration scope** and stays Python-side in the delegation shim. PyYAML's emitter carries its own float representer (`repr(x).lower()` plus the `.0e` fixup) and scalar-quoting rules, so its byte output — which is the contract, re-read by the loader and by humans — is never reimplemented. The differential pins a Rust-loaded loop re-saved by the Python save path re-loading identically (the U3 round-trip scenario) and compares the emitted bytes byte-for-byte against the pinned oracle (7 branch-covering loops). |

Contract construction is likewise by *identity*, not transcription: the
loaders call the same `DesignRules` / `NetClassRules` / `Loop` / `LoopPin` /
`LoopEvent` / `LoopCollection` constructors the pre-migration code called,
with kwargs assembled in Rust. This makes construction parity exact
*including* the pyo3 argument-conversion `TypeError` texts, which a Rust-side
re-extraction would have silently reworded.

What did move: field mapping, per-key defaults and their evaluation order,
`str()`/`float()` coercion, case-insensitive enum resolution over
`members()`, every user-facing error string, the `class_pairs` key
split/sort/dedup, the skipped-key warning (through the production logger
name), README skipping, `except Exception` wrapping with `raise ... from`
cause chaining. The load path is Rust; the save path is Python (KTD7).

## Induction applicability

**Mathematical induction is not applicable to these modules.** No function is
recursive, and no function iterates over a dimension whose *correctness*
depends on a size parameter:

- `load_netclass_rules` performs two independent passes (classes, class
  pairs). Each iteration writes one dict entry from one document entry; there
  is no cross-element interaction beyond last-write-wins on a colliding
  canonical key, which is the document's own semantics and is pinned by the
  `pair_key_sorting` differential case.
- `load_loop_from_dict` is a fixed sequence of key reads; the only loop is
  over `pins`, and each pin is constructed from its own entry alone.
- `_parse_loop_type` / `_parse_priority` scan a FIXED-size member table (13
  and 4 members); the scan terminates at the first value match and the tables
  are compile-time constants, so there is no size parameter to induct over.
- `load_loop_collection` iterates a caller-provided file list, but the
  per-file operation is independent of the list's length; the only
  order-dependent behaviour is `add_loop`'s duplicate-name rejection, which
  the differential pins directly
  (`test_load_loop_collection_duplicate_names_wrap_identically`).

These are data/format loaders, so per the plan's R1e a **structural proof**
is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the migrated
behaviour is bit-identical to the pinned pre-migration Python
(`packages/temper-placer/tests/io/_netclass_loader_py_oracle.py` and
`_loop_loader_py_oracle.py`, commit `e90991a2a`), on both the success and
the failure path.

*Proof by structural cases.*

1. **Document ingestion.** Both sides call `open(path)` and hand the *file
   object* (not its text) to `yaml.safe_load`. The file object is
   load-bearing: PyYAML embeds the stream's name in its error text, so the
   `Invalid YAML in <path>: <detail>` message is reproduced verbatim only
   this way (pinned by `test_load_loop_template_invalid_yaml_parity`). The
   parsed document is therefore the *same Python object graph* on both
   sides, so every downstream difference is attributable to this module.

2. **`load_netclass_rules` — scalars and classes.**
   `data["default_clearance_mm"]` is a subscript, not a `.get`, so a missing
   key raises `KeyError('default_clearance_mm')`; the port uses
   `Bound::get_item`, which is `__getitem__`. The eleven `NetClassRules`
   kwargs are read in the oracle's order with the oracle's defaults, and the
   four `default_*` fallbacks are read *from the `DesignRules` instance*
   after `default_clearance` has been overwritten — so `clearance` falls
   through to the document's value, not the constructor's. Property N2 pins
   exactly this ordering; the "constant default" mutant fails it.

3. **`load_netclass_rules` — class pairs.** `pair_key.split("-")` is the
   Python method (so a non-`str` key raises the same `AttributeError`);
   arity != 2 emits `logger.warning("Invalid class_pairs key '%s' —
   skipping", pair_key)` through the logger NAMED
   `temper_placer.io.netclass_loader` — the pre-migration module's own
   `__name__` — with `%`-style lazy args, and continues. `tuple(sorted([a,
   b]))` is performed by CPython's `list.sort`, so ordering is Python's
   string comparison rather than Rust's `Ord` (these agree on ASCII and, as
   it happens, on all UTF-8, but the port does not rely on that). The
   resulting dict is assigned to `dr.class_pairs` AND returned, so
   `result.class_pairs is result.design_rules.class_pairs` — an aliasing
   invariant consumers depend on, pinned by property N5 and by
   `test_netclass_class_pairs_is_the_same_object_on_design_rules`.

4. **`load_loop_from_dict`.** The required-field block is a `KeyError`-only
   catch producing `Missing required field: 'name'` (the KeyError's `str`,
   i.e. the quoted key) with the KeyError preserved as `__cause__`; any other
   exception from that block propagates untouched. The optional fields are
   read in the oracle's exact order — `pins`, `components`, `nets`,
   `max_area_mm2`, `priority`, `events`, `return_layer`, `return_net` — which
   fixes *which* error a doubly-malformed document raises. `float(...)` is
   CPython's builtin, not a Rust parse, so `"1e3"`, `-0.0`, `5e-324` and
   `1.7976931348623157e308` all land on the identical bit pattern (asserted
   as `float.hex()` in the differential).

5. **Enum resolution.** `_parse_loop_type` / `_parse_priority` iterate
   `LoopType.members()` / `LoopPriority.members()` — the same declaration-order
   staticmethod the pre-migration module was already adapted to use in the
   Phase-2 loop migration — and compare `member.value == type_str.lower()`
   with the oracle's operand order. The failure text
   (`Unknown loop type: X. Valid types: ['commutation', ...]`) is built by
   taking `repr()` of a real Python list of the member values, so the
   rendering is CPython's, and it is additionally pinned as a literal string
   by `test_loop_load_error_message_texts_are_pinned`.

6. **`load_loop_collection`.** Existence and directory checks precede
   construction; `name or directory.name` is replicated as an emptiness
   test; `sorted(directory.glob(pattern))` is delegated; the three README
   names are compared against a lowercased filename; and every `Exception`
   (not `BaseException`) raised while loading or adding a template is
   re-raised as `Failed to load <path>: <str(e)>` with the original as
   `__cause__`. `LoopCollection.add_loop`'s duplicate-name `ValueError` falls
   inside that wrap, which the differential pins directly.

7. **`save_loop_to_yaml`.** Python-side in the delegation shim per KTD7 —
   the save path is outside the loaders' migration scope. The shim's
   function is the pre-migration implementation operating on the Rust
   `Loop` pyclass surface, so its correctness is the correctness of the
   pyclass attribute surface it reads (`name`, `loop_type.value`,
   `components`, `pins[].component_ref/pin_name/net_name`, `nets`,
   `max_area_mm2`, `priority.value`, the six `events` fields,
   `return_layer`, `return_net`): the emitted mapping is built in the
   oracle's insertion order (`sort_keys=False` makes insertion order the
   emitted key order), with the oracle's exact conditionals: truthiness for
   `components`/`pins`/`nets`/`net`/`return_layer`/`return_net`, and `is
   not None` for the six event fields — the distinction that keeps a `0.0`
   slew rate alive. `path.parent.mkdir(parents=True, exist_ok=True)` and
   `yaml.dump(..., default_flow_style=False, sort_keys=False,
   allow_unicode=True)` are the same calls, so the output is byte-identical
   by construction. The differential drives the shim function and asserts
   the emitted bytes byte-for-byte against the pinned oracle, and the
   round-trip tests pin a Rust-loaded loop re-saved by this Python save
   path re-loading identically (the U3 scenario). The `is not None` guard
   is demonstrably load-bearing: a truthiness mutant on the shim's save
   fails `test_save_loop_to_yaml_byte_identical[zero_valued_events]` and
   `..._round_trip_parity[zero_valued_events]` (verified 2026-08-04).

8. **`NetClassRulesDict`.** Replaces the two-field mutable dataclass:
   attribute get/set on both fields, field-wise `__eq__` restricted to the
   same type, and a dataclass-shaped `__repr__`. Note that the pre-migration
   `repr` already embedded an object address (via `DesignRules`, which has no
   custom `repr`), so `repr` was never a stable comparison surface for this
   type and is not claimed as one.

## Documented deviations (per R1, recorded here)

- **`LoopLoadError` class identity.** The exception is now defined in Rust.
  It still subclasses `Exception` and its `__module__` is restored to
  `temper_placer.io.loop_loader` at registration, so `except LoopLoadError`,
  `pytest.raises`, `repr(cls)` and tracebacks are unchanged — but it is not
  the same class *object* the pre-migration module defined. Pickling the
  class, or comparing it by identity against a separately-imported copy,
  would observe the change. Verified 2026-08-04 that no consumer in `src/`,
  `tests/` or `scripts/` does either.
- **`__context__` is not set on the wrap paths.** `raise ... from e` on the
  oracle is executed from inside an `except` block, so CPython additionally
  records the exception being handled as `__context__` (the same object as
  `__cause__`). The Rust loader constructs the new error with no active
  exception state, so `__context__` is `None`. Traceback output is identical
  either way — with `__cause__` set, `__context__` is never rendered — and
  the differential compares `__cause__` presence/type/message and
  `__suppress_context__` (both sides reproduce `raise ... from e` on all
  four wrap paths: KeyError, Invalid-YAML, Failed-to-load-collection,
  duplicate-name) but deliberately not `__context__`. Pinned by the extended
  `_raised()` comparator in the differential.
- **`NetClassRulesDict` is a pyclass, not a dataclass.** Attribute surface,
  mutability, `__eq__` and `__repr__` are preserved;
  `dataclasses.fields()` / `dataclasses.asdict()` / `dataclasses.replace()`
  no longer apply. No consumer uses them (verified 2026-08-04). Its
  `__module__` is restored to `temper_placer.io.netclass_loader` at
  registration (like `LoopLoadError`), so the class pickles by reference and
  `repr(cls)` reads unchanged; and an explicit `__copy__` keeps
  `copy.copy(result)` shallow-copying with both fields shared, exactly like
  the dataclass. Pickling an *instance* still fails with `TypeError` — the
  held `DesignRules` is itself a pyclass with no pickle support — but the
  pre-migration dataclass fails identically on the same field, so this is
  parity, not a regression. Pinned by
  `test_netclass_rules_dict_identity_and_module` and
  `test_netclass_rules_dict_pickles_and_shallow_copies_like_the_dataclass`.
- **`inspect.signature` degrades to pyo3's `__text_signature__`.**
  `inspect.signature(load_loop_from_dict)` / `(load_loop_collection)` now
  returns `(data, source=Ellipsis)`-style signatures with no annotations and
  no literal defaults, where the pre-migration Python functions carried full
  annotations and literal defaults. This is an inherent property of the pyo3
  boundary (`__text_signature__` is a plain-text approximation) and is NOT
  fixable without keeping a Python wrapper around every function — which
  would defeat the migration. Verified 2026-08-04 that no consumer in
  `src/`, `tests/` or `scripts/` calls `inspect.signature` /
  `inspect.getfullargspec` on any of the four loaders (every caller —
  the in-repo consumers, the differential and the PBT suites — drives them
  with concrete positional/keyword arguments). Any future
  tooling that introspects signatures on these functions must read the
  pyo3 `__text_signature__` and treat annotations as unavailable.
- **Traceback frame provenance moves to the extension.** Loader errors now
  originate at the pyo3 boundary, so `__traceback__` frames name the
  compiled `temper_design_bundle_python` extension rather than
  `loop_loader.py` / `netclass_loader.py` line numbers. Traceback TEXT
  (exception type, message, cause chain) is unchanged; only the
  frame-filename/line attributes differ. Any CI log greps that match on the
  pre-migration `.py` frame filenames will stop matching and must grep on
  the error text or exception type instead. This is inherent to a compiled
  extension and not fixable at this boundary.
- **Argument-type-check precedence and message.** `source`, `name` and
  `description` are typed `String` at the pyo3 boundary, so a non-`str`
  argument raises `TypeError` with the identical pyo3 message
  (`'int' object is not an instance of 'str'`) but *before* the body runs —
  where the oracle would have raised its own `LoopLoadError` first if `data`
  was also invalid. Message identical, precedence different. `pattern` is the
  one exception: the oracle passes it straight to `pathlib.Path.glob` (kept
  Python-side for its intricate pattern semantics), whose message is
  `expected str, bytes or os.PathLike object, not int`, while the Rust
  boundary raises the pyo3 message — the messages DIFFER by design
  (pathlib.glob semantics are not re-implemented). The divergence is pinned,
  not just described, by
  `test_load_loop_collection_pattern_type_message_divergence_pinned`, which
  asserts each side's exact message text.
- **`.items()` unpacking text.** Iterating a mapping's `.items()` uses pyo3
  2-tuple extraction, so a pathological custom mapping yielding non-pairs
  reports `expected a sequence of length 2` where CPython's tuple unpacking
  reports `too many values to unpack`. Unreachable for `yaml.safe_load`
  output, which always yields 2-tuples.
- **Private helpers removed from the Python module.** `_parse_events`,
  `_parse_pins`, `_parse_loop_type` and `_parse_priority` moved into the
  crate and are no longer importable from `temper_placer.io.loop_loader`.
  They were private and had no importers (verified 2026-08-04); the same
  precedent as `core/priority.py`.
- **PyYAML line-break lossiness (pre-existing, NOT introduced).** A scalar
  containing U+000A/U+000D/U+0085/U+2028/U+2029 does not survive
  `dump` → `safe_load` verbatim, because YAML's reader normalizes line
  breaks. This is a property of the kept tokenizer/emitter and held
  identically before the migration;
  `test_yaml_line_break_characters_are_equally_lossy_on_both_sides` pins the
  two implementations agreeing on such input, and the PBT round-trip
  relations state the corresponding bound explicitly rather than silently
  excluding the characters.

## Evidence

- **Differential (R1a / R1f, TDD red → green):**
  `packages/temper-placer/tests/io/test_loaders_rust_differential.py` — 171
  tests against the verbatim oracles `_netclass_loader_py_oracle.py` /
  `_loop_loader_py_oracle.py` (commit `e90991a2a`). Coverage: the shipped
  `configs/netclass_rules.yaml` field-for-field, 10 crafted netclass
  documents, 7 netclass error paths, the logger-warning record, 30 crafted
  loop documents, 22 loop error paths, all 5 shipped loop templates, 11
  collection behaviours, and 7 byte-for-byte emitter cases plus the round
  trip. Every float is compared as `float.hex()`; every non-float leaf
  carries its `type` in the comparison key, so an int/float drift cannot
  pass. **RED first:** the file failed to collect
  (`AttributeError: module 'temper_design_bundle_python' has no attribute
  'load_netclass_rules'`) before the Rust landed.
- **Anti-vacuity (the differential demonstrably bites).** Six independent
  mutations were built and run — five of `loaders.rs` and one on the Python
  save path; each was caught, and reverting restored green. All five load-path
  mutants were re-verified against the rebased tree on 2026-08-04:

  | Mutant | Change | Caught by |
  |--------|--------|-----------|
  | A | drop `sorted()` on class-pair keys | 3 tests — `test_netclass_real_fixture_bit_identical`, `test_netclass_real_fixture_class_pairs_exact`, `test_netclass_crafted_yaml_bit_identical[pair_key_sorting]` — the real fixture's four genuinely-unsorted pairs (`HighVoltage-GND`, `HighVoltage-FinePitch`, `HighVoltageIsolated-GND`, `HighVoltageIsolated-FinePitch`) plus the crafted `Zeta-Alpha`/`Alpha-Zeta` overwrite. `pair_key_arity` is excluded: its only well-formed pair keys are `A-B` and `-`, both already in sorted order, so dropping the sort changes nothing for it |
  | B | emitter uses truthiness instead of `is not None` for events | 2 tests — `test_save_loop_to_yaml_byte_identical[zero_valued_events]`, `..._round_trip_parity[zero_valued_events]` (verified 2026-08-04 against the Python-side save path) |
  | C | `max_area_mm2` default 100.0 → 10.0 | 57 tests |
  | D | drop `str()` coercion on the pin component | 3 tests, incl. `test_load_loop_template_yaml_11_booleans_parity` |
  | E | reword the unknown-priority message | 3 tests, incl. `test_loop_load_error_message_texts_are_pinned` |
  | F | README skip compares without lowercasing | 1 test — `test_load_loop_collection_readme_skip_parity` |

- **PBT (R1c):** `packages/temper-placer/tests/io/test_loaders_pbt.py` — 5
  hypothesis properties per module (N1–N5 for netclass, L1–L5 for loop), each
  with a `test_*_fails_for_<mutant>` vacuity mutant driven through the
  `_kernels` indirection (empty loader, constant default, defaults-only,
  unsorted keys, unaliased result, case-sensitive enum match, wrong defaults,
  rounding kernel, lossy emitter, first-file-only collection).
- **Metamorphic (R1d):** same file — 3 relations per module. MN1 mapping-order
  permutation (exact for content; `net_classes` *insertion order* follows the
  document and is explicitly NOT claimed invariant), MN2 pair-key reversal
  (exact), MN3 unmapped-key inertness (exact); ML1 dict-key-order permutation
  (exact), ML2 unrecognized-key inertness (exact), ML3 emitter byte
  idempotence (exact at byte level, bounded to the re-loaded loop because the
  emitter deliberately omits falsy fields). Two discriminating-input sanity
  tests prove neither relation set is vacuously satisfied.
- **Rust unit tests:** `loaders.rs::tests` — the event-field set and its
  ORDER (it is the emitted key order under `sort_keys=False`), the README
  skip list being lowercase (it is compared against a lowercased name), and
  the logger name matching the production module.
- **Rust practices (R1g):** every exported pyfunction is wrapped in
  `temper_py_bridge::catch_unwind(...)` via the local `guard` helper; no
  `unwrap`/`expect` anywhere (the crate denies both via `[lints.clippy]`);
  `cargo clippy --all-features --all-targets -- -D warnings` clean.
- **Performance A/B (R1b):** the loaders are registered as
  `("loaders", "loaders")` in `benchmarks/perf_ab.py::_BENCHMARKS`, so the
  Phase-0 hard gate measures them: the benchmark A/Bs the migrated loaders
  against the verbatim pre-migration oracle loaders on the repo's own
  shipped fixtures (a parity sanity assertion inside the harness fails the
  run if the arms disagree), and `scripts/pr_perf_compare.py` compares the
  emitted `rust_over_oracle_ratio` against the rolling main-branch median
  under `TIMING_MARGIN = 0.20`. These loaders are I/O-bound YAML parsing
  with no compute kernel (measured ratio ≈ 1.0 — both arms share PyYAML and
  the contract constructors; the delta is the orchestration layer), so per
  the program's R2 this is the **"no regression beyond noise"** arm, NOT a
  speedup claim. The key is reported as NEW_BENCHMARK (not a failure) until
  main's registry carries it and baseline rows are captured. A secondary,
  manual measurement path also exists: `temper_placer.profiling.
  pipeline_metrics::profile_loaders`, wired into
  `temper profile run --module loaders|all` and emitting
  `module="loaders"`, `stage="loaders"`, metrics `netclass_load_ms` /
  `loop_collection_load_ms` / `total_ms`.
- **R1h (physics discipline): NOT APPLICABLE.** These are data/format
  loaders. They perform no physics, encode no geometric constraint, and
  compute no value that a post-solve audit could recompute from coordinates —
  the single arithmetic operation in either module is `float(...)` coercion.
  The R24 Chebyshev-soundness / BMC-exhaustive / post-solve-audit obligations
  have no referent here.
- **Consumer suites run unchanged against the migrated loaders:**
  `tests/io/` (481 passed, 12 skipped, 1 xfailed), `tests/core` + `tests/pcl`
  (932 passed), `tests/io/test_netclass_loader.py`,
  `tests/io/test_loop_loader.py`, `tests/core/test_design_rules_field_parity.py`,
  `tests/router_v6/test_layer_assignment_ssot.py`,
  `tests/router_v6/test_phase1_anti_false_zero.py`.
# Manufacturing tolerance model — Verification

The manufacturing tolerance model (`src/manufacturing_tolerances.rs`) is the
Wave 4 Phase 4 leftovers slice's first migration: two plain `Enum`s
(`CopperWeight`, `LayerType`), two dataclasses (`ToleranceTable`,
`FeatureTolerance`) and the `ToleranceAnalyzer` with its two closed-form
analysis methods, ported from
`temper_placer/manufacturing/tolerances.py` (the Python module is now a
pure-delegation re-export of the `temper_design_bundle_python` pyclasses).

## Induction applicability

**Mathematical induction is not applicable to this module.** None of its
functions are recursive, and none iterate over a dimension whose
correctness depends on a size parameter:

- `ToleranceAnalyzer::analyze_clearance` / `analyze_trace` are two closed-form
  arithmetic expressions (`2 * etch + reg`, `width ± etch`) with a constant
  table lookup — no loop, no recursion.
- The enum value-construction `#[new]`s scan a fixed 2-3 member candidate
  list — constant, not size-parameterized.
- `ToleranceTable`'s default dicts are built with a fixed 2-3 item sequence.

The module is data-only plus closed-form arithmetic. Per the plan's R1e, a
**structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass
behaviour is bit-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/manufacturing/_tolerances_py_oracle.py`,
commit `6290942be`).

*Proof by structural cases.*

1. **Enum members (`CopperWeight`, `LayerType`).** Both sides expose the
   same closed member sets with the same values (floats `0.5/1.0/2.0`,
   strs `"outer"/"inner"`), the same `str(member)` (`"CopperWeight.HALF_OZ"`
   — plain Enum, NOT bare-value IntEnum), the same `repr(member)`
   (`<CopperWeight.HALF_OZ: 0.5>` / `<LayerType.OUTER: 'outer'>`, values
   rendered by the CPython `repr(float)`/`repr(str)` rules), and the same
   `Cls(value)` construction. Value construction compares with CPython's own
   `==` (via `PyObject_RichCompareBool`), so `CopperWeight(1)` resolves to
   the `1.0` member exactly as Python's Enum does; the invalid-value
   `ValueError` text is byte-identical because it renders the *original*
   object with CPython `repr` (`999 is not a valid CopperWeight` for an int,
   `'x' is not a valid LayerType` for a str — the repr carries the quotes a
   str value needs). IEEE-754 and CPython repr rendering are both
   deterministic, so each member's surface matches bit-for-bit. Members are
   hashable/eq (`#[pyclass(frozen, eq, hash)]`), so dict-key usage — the
   load-bearing consumer behaviour — works identically.

2. **`ToleranceTable`.** The `etch_tolerance`/`registration` dicts are real
   Python dicts (the default factories build exactly the oracle's
   `default_factory` entries, keyed by the pyclass enum members), so
   lookup, insertion order and repr are CPython's own. The dataclass
   constructor signature, the `solder_mask_registration` default `0.075`,
   the repr, and the three-field equality all match the oracle.

3. **`ToleranceAnalyzer::analyze_clearance` / `analyze_trace`.** The dict
   lookup is CPython's own `dict.get` (via `PyDict::get_item`), so a missing
   key returns the oracle's fallback constants (`0.05` etch — the SAME
   constant in both methods, pinned by the clearance-side fallback
   differential case — and `0.1` registration) and an unhashable key raises
   CPython's own `TypeError: unhashable type: 'X'`. The arithmetic is
   transcribed verbatim with the oracle's parenthesization (`2 * etch +
   reg` — IEEE-754 left-associative — and `width ± etch`); IEEE-754 basic
   operations are deterministic, so every derived field of the returned
   `FeatureTolerance` is bit-identical. `feature_type` strings are the
   oracle's literals.

4. **`FeatureTolerance`.** Six fields, dataclass equality, dataclass repr
   with CPython str/float rendering — all match. `nominal_value` and the
   clearance-arm `worst_case_max` carry the ORIGINAL caller object (the
   oracle's dataclass stores the argument unmodified): an int clearance
   stays int (repr `1`, not `1.0`), equality on those fields runs through
   CPython's own `==`, and repr renders them via CPython's `repr`. The
   arithmetic-derived fields are `f64` — identical to the oracle whenever
   the table values are floats (the pinned envelope; see the deviations
   below for int table values). `from_py_object` is dropped on the pyclass
   (it requires `Clone`, which `Py<PyAny>` fields cannot provide; nothing
   in the crate or the shim extracts a `FeatureTolerance` from an
   argument).

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/manufacturing/test_tolerances_rust_differential.py`
  (34 tests; the RED state was demonstrated: the file fails to collect
  with `AttributeError: module 'temper_design_bundle_python' has no
  attribute 'CopperWeight'` before the Rust pyclasses landed). The
  adversarial-review additions (2026-08-05): the clearance-side
  copper-weight fallback case (discriminates the shipped `0.05→0.06`
  mutant), int-clearance/width field-parity rows with the R1a type-aware
  comparison key (concrete type alongside `float.hex()` for
  `nominal_value`/`worst_case_max`), and the int-input repr-parity test.
- PBT (R1c): `test_tolerances_pbt.py` — 10 hypothesis properties
  (P1/P2/P3/P4/P5/P5b/P6/P6b/P7 + MR1-MR4), each fail-capable.
- Metamorphic (R1d): `test_tolerances_pbt.py` — MR1 (enum
  value-construction commutativity), MR2 (dict insertion-order permutation
  invariance), MR3 (fallback ≡ explicit default), MR4 (etch monotonicity).
- Anti-vacuity: **the original 11-mutant claim contained one false
  positive — the `0.05→0.06` etch-fallback mutant SHIPPED.** The original
  fallback test drove `analyze_trace` only, whose fallback is `0.05` on
  both sides, so the clearance-side `0.06` sailed through the campaign and
  the doc recorded it as caught. The adversarial review (2026-08-05) found
  the shipped mutant and the false claim; the clearance-side fallback case
  now discriminates it. The full campaign was RE-RUN against the fixed
  tree with an explicit revert verification (after each mutant the source
  was restored and `git diff` confirmed empty before the next mutant; see
  `docs/evidence/2026-08-05-wave4-phase4-leftovers-adversarial-fixes.md`):
  all 11 mutants caught — etch fallback `0.05→0.06` (now caught by the
  clearance-side case), registration fallback `0.1→0.2`, `2*etch+reg →
  etch+reg`, clearance `worst_case_min −→ +`, trace `width−etch →
  width+etch`, trace `worst_case_max → nominal`, default etch `0.025→0.02`,
  default registration `0.1→0.01`, enum value `0.5→0.4`, `feature_type`
  `"clearance"→"trace_width"`, dict-miss fallback `→0.0`.
- Rust unit tests: `manufacturing_tolerances.rs::py_repr_tests` — the
  CPython str/float repr divergence classes (B9/B10) for the values that
  appear in this module's reprs.
- Rust practices (R1g): borrow over clone throughout; no `unwrap`/`expect`
  in non-test code; `cargo clippy --release --features python` clean (0
  warnings).
- Performance A/B (R1b): this is a pure-data contract migration with no
  compute kernel — the two analysis methods are O(1) closed-form arithmetic.
  Per the plan's R2 this is the **"no regression beyond noise"** comparison:
  the migrated analyzer is a pyo3 method call on the same Python dicts the
  oracle used, so there is no measurable kernel to benchmark; no speedup is
  claimed. (No `perf_ab` registration: the surface has no production hot
  path — the only consumers are the tests and the
  `manufacturing/__init__.py` re-export.)
- R1h (physics discipline): NOT APPLICABLE. Tolerance analysis is
  uncertainty/probability compute in the *domain* sense (etch/registration
  variability), but none of it gates a CP-SAT constraint on a physics
  quantity: no constraint is encoded, no post-solve audit has a referent,
  and the R24 Chebyshev/BMC/post-solve obligations do not apply. The
  R1h determination is recorded per module: `tolerances.py` — N/A (no
  physics-gated constraint); `monte_carlo.py` — N/A (the simulator gates
  nothing; it reports a yield estimate — see the monte_carlo section below).

## Documented deviations (per R1, recorded here)

1. **Enum singleton identity.** Python's `Enum` returns a *cached singleton*
   from `Cls(value)` (`CopperWeight(1.0) is CopperWeight.ONE_OZ` is True);
   the pyo3 pyclass constructs a fresh instance per call (attribute access
   `CopperWeight.ONE_OZ` is still identity-stable — pyo3 caches the class
   attribute). eq/hash — the load-bearing dict-key contract — are
   unaffected (`d[CopperWeight(1.0)]` resolves). No in-repo consumer relies
   on `is` identity of constructor results (verified 2026-08-04: consumers
   use members as dict keys or pass them through the analyzer).
2. **Class-level Enum iteration** (`for m in CopperWeight:`) is unavailable
   on pyo3 enums (no metaclass hook); `getattr`-based access covers every
   member in the differential suite. No consumer iterates these enums at
   class level.
3. **`ToleranceAnalyzer()` default table is per-instance.** The Python
   oracle evaluates `table: ToleranceTable = ToleranceTable()` once at
   definition time and shares that instance across all default analyzers;
   the pyclass builds a fresh default per instance. The shared-instance
   behaviour is unobservable — no consumer mutates the table — so it is not
   covered by the differential.
4. **Non-numeric dict values.** A dict value that is not a float raises a
   pyo3 `TypeError` from the f64 extraction where the oracle's arithmetic
   would raise a different-text `TypeError`. The oracle itself is broken on
   such input; the differential does not cover it.
5. **Int table VALUES are outside the pinned envelope.** The declared
   contract types the `etch_tolerance`/`registration` dict values as
   `float` (the oracle's own annotations), and every test fixture uses
   floats. With an int-valued dict entry, the oracle's derived fields
   (`tolerance_plus`/`tolerance_minus` and the trace-arm `worst_case_max`)
   stay int through Python arithmetic while the Rust side computes them in
   `f64` — a repr-level type difference on inputs outside the contract.
   The int *argument* path (int clearances/widths) IS pinned: the oracle's
   passthrough fields (`nominal_value`, clearance-arm `worst_case_max`)
   preserve the original object on both sides.
6. **`CopperWeight(True)`.** Python's Enum resolves `True` to the `1.0`
   member (`True == 1.0`); the pyclass `#[new]` receives the bool and
   CPython's `==` compares it against the float candidates — this path is
   covered by the same rich-compare, so it matches. No consumer relies on
   it.

---

# Monte-Carlo tolerance simulator — Verification

The Monte-Carlo simulator (`src/manufacturing_monte_carlo.rs`) is the Wave 4
Phase 4 leftovers slice's third migration: the four dataclasses
(`DistributionParams`, `ManufacturingVariables`, `MonteCarloConfig`,
`MonteCarloResult`) and the `MonteCarloSimulator` with its sampling loop and
the clearance-simulation kernel, ported from
`temper_placer/manufacturing/monte_carlo.py` (the Python module is now a
pure-delegation re-export of the `temper_design_bundle_python` pyclasses).
Home crate: `temper-design-bundle` — the data-contract home (the sibling
`manufacturing/tolerances.py` migration landed here; the simulator's
config/result types are contract-adjacent, and the RNG boundary lives in
numpy, not in a geometry crate).

## Induction applicability

**Mathematical induction IS applicable to the kernel and is discharged
below.** `clearance_min_distances` is an iterative fold over the sample
count S and the N×N component-pair grid; the claim is that every iteration
produces bit-identical values to numpy's elementwise chain on the same
inputs.

*Induction claim (K(S, N)): for samples `0..S` and pairs `0..N²`, the Rust
kernel's per-sample min distances equal `np.min(dist, axis=(1,2))` for the
oracle's construction, bit-for-bit.*

*Base case.* S = 0: both sides produce an empty vector (the oracle's
`np.min` over `(0, N, N)` reduces zero slices — no elements). N = 0: both
sides raise the identical `ValueError` (see the error-parity section). For
S ≥ 1, N ≥ 1 the diagonal pair (i == j) is masked to exactly `1e6` on both
sides, so the fold always has at least one element and the accumulator
initialisation (`+∞`) can never leak into the result.

*Step.* Each (si, i, j) iteration computes the oracle's elementwise chain
with the identical parenthesization, each a single IEEE-754 double
operation:

- `s_pos = positions + stack([reg_x, reg_y])` — one `f64` add per
  coordinate (numpy's add on float64 operands is one correctly-rounded op;
  dtype promotion to float64 is exact for float32→float64 and for ints
  within the exact-int range, while int64 leaves beyond 2^53 round on BOTH
  sides through the identical conversion — the parity claim, not exactness,
  holds there);
- `s_widths = bounds + 2 * etch` — one multiply by the exact power of two
  `2.0` (no rounding) followed by one add;
- `dx/dy = |a - b|`, `mw/mh = (a + b) / 2.0` — one subtract, one add, one
  exact halving;
- `sep = dx - mw` — one subtract;
- `dist = np.maximum(sep_x, sep_y)` — reproduced by `np_max`: NaN when
  either operand is NaN (numpy's `maximum` propagates NaN, Rust's
  `f64::max` discards it — the divergence class), else the larger operand.
  The `b > a` tie-break is value-identical to numpy for every value this
  construction can produce: `sep` can never be `-0.0` (`|a - b|` is `+0.0`
  or positive; `0.0 - 0.0` and `0.0 - (-0.0)` are both `+0.0` in
  round-to-nearest), so the only tie numpy's max can see is equal positives,
  where either choice has the same bits;
- the eye-mask `np.where(mask, 1e6, dist)` — `1e6` is exact in f64, applied
  to exactly the i == j entries;
- the reduction `np.min(dist, axis=(1,2))` — `np_min` is NaN-propagating
  (same divergence class, verified against numpy: `np.min` over a NaN
  element returns NaN regardless of order) and order-independent for every
  other value the construction produces (no `-0.0` candidates — the mask
  contributes `1e6`, positive; no NaN-free order sensitivity in IEEE min).

Rust does not fuse multiply-add without an explicit `mul_add` (rustc
defaults to strict IEEE, no fast-math), so each op's rounding is numpy's.
By induction, K(S, N) holds for all S, N; the fold is exact and the kernel
output is bit-identical to the oracle's `min_dists`.

The module's remaining structure (the sampling loop and the aggregation
tail) is not size-parameterized computation: the sampling loop calls numpy's
Generator for each of six fixed parameter names, and the aggregation tail
calls numpy itself (see below).

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass
behaviour is bit-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/manufacturing/_monte_carlo_py_oracle.py`,
commit `58b302ce8`).

*Proof by structural cases.*

1. **Dataclasses.** `DistributionParams`, `ManufacturingVariables`,
   `MonteCarloConfig`, `MonteCarloResult` store every field as `Py<PyAny>`
   (type-preserving: an int `mean=5` stays an int, exactly as the Python
   dataclass stores it), with `#[pyo3(get, set)]` mutation and a
   `__dict__` (`#[pyclass(dict)]`) so attribute injection still works.
   Defaults are built by the type-preserving `opt_or` helper: `0.0`,
   `"normal"`, `1000`, `42`, the five-percentile tuple. `__repr__` is
   assembled by the crate's `dataclass_repr`/`repr_of` helpers (CPython's
   own `repr` on every stored object), `__eq__` by `dataclass_eq`
   (field-tuple comparison with the dataclass's `other.__class__ is
   self.__class__` gate), and `__hash__` raises CPython's exact
   `unhashable type: 'X'` — the mutable-dataclass `__hash__ = None`
   contract.

2. **The RNG stream (KTD9 boundary).** `MonteCarloSimulator.__init__`
   builds the generator with numpy's own `np.random.default_rng(config.seed)`
   and stores it as `_rng`; `sample_parameters` calls
   `rng.normal(mean, std_dev, size=n)` / `rng.uniform(min_v, max_v, size=n)`
   through Python with the oracle's exact arguments (the uniform fallback
   `mean ± 1.0` is Python arithmetic on the stored objects) over the six
   parameter names in the oracle's declaration order, building a real
   Python dict in that order. Ziggurat/PCG64 are numpy internals — no
   independent implementation is bit-reproducible — so the stream is
   numpy's on both sides, by construction; the differential pins it (same
   seed ⇒ identical arrays; consecutive calls advance identically; the
   error path consumes draws identically — `test_rng_state_after_error_matches`).

3. **The clearance kernel.** The induction proof above. The kernel's only
   inputs are the sampled arrays and the caller's `positions`/`bounds`,
   widened to f64 exactly (float32→float64 lossless; ints via Python's
   `float()`), and its only output is the per-sample min-distance vector —
   everything downstream runs through numpy.

4. **The aggregation tail (KTD9 boundary).** `np.asarray(min_dists)`,
   `min_dists >= required_clearance`, `passes.astype(np.float32)`,
   `np.mean` (yield and stats) and `np.std` are numpy calls on both sides
   with the oracle's call order. numpy's `mean`/`std` use pairwise
   summation whose block size is SIMD-dispatch-dependent (build and
   platform), so an independent Rust replica would be bit-exact on one
   build and divergent on another — a library semantic, not portable
   compute. Because the kernel output is bit-identical (case 3), the numpy
   tail is bit-identical by construction. The `float()` conversions (on
   `np.float32` yield and `np.float64` stats) are exact widenings.

5. **Error parity.** `N == 0` raises numpy's exact
   `ValueError: zero-size array to reduction operation minimum which has no
   identity` at the same point in the call sequence as the oracle's
   `np.min` (after sampling — the RNG stream state at raise time is
   identical); 0-D/1-D `positions`/`bounds` raise the oracle's fancy-index
   `IndexError` texts (`array is N-dimensional, but 2/3 were indexed` — the
   `None` index does not count), and plain lists raise numpy's
   `TypeError: list indices must be integers or slices, not tuple`. The
   INNER dimension is pinned too (added 2026-08-05 after an adversarial
   review found `check_*_ndim` never examined it): positions trailing dim 1
   broadcasts (`x → [x, x]`, exactly numpy's size-1 axis broadcast), dims 0
   and ≥3 raise numpy's `ValueError: operands could not be broadcast
   together with shapes (1,N,k) (S,1,2) ` (exact text, trailing space
   included), bounds trailing dims 0/1 raise numpy's `IndexError: index
   0/1 is out of bounds for axis 1 with size 0/1`, and bounds dims ≥3 are
   tolerated (the oracle indexes only columns 0 and 1). All verified
   byte-for-byte against numpy 2.3.5 by the differential.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/manufacturing/test_monte_carlo_rust_differential.py`
  (39 tests; the RED state was demonstrated: the file fails to collect with
  `AttributeError: module 'temper_design_bundle_python' has no attribute
  'MonteCarloSimulator'` before the Rust pyclasses landed). Comparison
  conventions: numpy arrays as `(dtype, shape, tobytes())`, floats via
  `float.hex()` (NaN included — `'nan' == 'nan'`), concrete leaf types in
  the keys, errors by (type, message) via `canon_call`. The 2026-08-05
  additions: the ragged-inner-dimension error cases above (RED before the
  fix: the kernel silently computed on (N,3) positions and panicked —
  `PanicException` — on (N,1) bounds) and the two tolerated-edge parity
  cases; the tautological `... or True` assertion in
  `test_sampling_parity_all_normal` was replaced with the byte-exact
  stream comparison plus a non-degeneracy guard.
- PBT (R1c): `test_monte_carlo_pbt.py` — 8 hypothesis properties
  (P1 closed-form kernel, P2 clearance monotonicity on one stream, P3
  two-component closed form with the float-computed separation, P4
  same-stream etch comparison, P5/P5b uniform bounds incl. the fallback,
  P6 shapes/dtypes incl. n=0, P7 result metadata), each fail-capable.
- Metamorphic (R1d): `test_monte_carlo_pbt.py` — MR1 (seed invariance
  without variables — no RNG consumption), MR2 (component-order permutation
  invariance — bit-exact, the pair multiset is unchanged), MR3
  (uniform-fallback ≡ explicit `mean ± 1.0` bounds — identical stream,
  bit-identical draws), MR4 (power-of-two scaling invariance — every IEEE
  op on `2**m`-scaled operands is itself an exponent shift, so stats scale
  bit-exactly and yield is invariant; a translation MR was deliberately NOT
  claimed — `(p + t) + reg` rounds differently from `p + (reg + t)`).
- Anti-vacuity: 10 mutants, all caught by the differential/PBT suites:
  `np_max` NaN propagation dropped (caught by the NaN y-column case),
  `np_max` last-wins (14 failures), `reg_y` replaced by `reg_x`, self-mask
  `1e6 → 0.0`, min-reduce init `+∞ → 0.0`, etch dropped from heights,
  `bounds + 2*etch` reparenthesized, `np_min` NaN propagation dropped
  (caught by the NaN x/y-column cases), `sep_y` dropped, `>=` → `>` (the
  exact-equality boundary). **Re-verified 2026-08-05 with an explicit
  revert verification** (each mutant applied to the Rust source, the
  rebuilt extension run against the suites, the failure confirmed, the
  source restored, and `git diff` confirmed EMPTY before the next mutant):
  10/10 caught. Note on the last-wins mutant: the `>=` tie-break variant is
  value-identical on the kernel's operand domain (separations can never be
  -0.0 — the module docstring's argument), so it cannot be caught by the
  differential; the campaign mutant is the always-`b` variant, which is
  caught (3 failures). Full log in
  `docs/evidence/2026-08-05-wave4-phase4-leftovers-adversarial-fixes.md`.
- Rust unit tests: `manufacturing_monte_carlo.rs::kernel_tests` — NaN
  propagation both sides for `np_max`/`np_min`, the signed-zero tie bits,
  the masked diagonal, the sentinel single-component case, etch expansion,
  NaN-through-reduction.
- Rust practices (R1g): no `unwrap`/`expect` in non-test code; `PyResult`
  everywhere; `cargo clippy --release --features python` clean (0 warnings);
  the pyo3 boundary methods are `catch_unwind`-wrapped by pyo3 0.29's
  generated trampolines.
- Performance A/B (R1b): the kernel is O(S·N²) real compute — but with no
  production consumers (the module's only callers are the tests and the
  `manufacturing/monte_carlo.py` re-export), a `perf_ab` registration would
  measure a synthetic hot path. Per the plan's R2 this is the
  **"no regression beyond noise"** arm: the migrated simulator calls numpy
  for sampling and aggregation exactly as the oracle did, and the kernel is
  bit-identical; no speedup is claimed. (No `perf_ab` registration —
  recorded, not skipped.)
- R1h (physics discipline): NOT APPLICABLE. `run_clearance_simulation`
  computes a yield *estimate*; it encodes no CP-SAT constraint gating a
  physics quantity, computes no quantity a post-solve audit could recompute
  from placement coordinates, and feeds no solver. The R24
  Chebyshev/BMC/post-solve obligations have no referent. (Recorded per the
  R1h dispatch instruction: monte_carlo/tolerances are uncertainty/
  probability compute — this module gates nothing.)

## Documented deviations (per R1, recorded here)

1. **`MonteCarloSimulator(variables)` default config is per-instance.** The
   Python oracle evaluates `config: MonteCarloConfig = MonteCarloConfig()`
   once at definition time and shares that instance across all
   default-config simulators (mutation of it would leak across simulators —
   a footgun, not a contract); the pyclass builds a fresh default per
   construction. Unobservable through any value a consumer reads — the
   differential compares full behavior with an explicit default-config
   construction (`test_run_parity_default_config`). A `LazyLock<Py<...>>`
   static is not `Sync` because the config holds a Python tuple.
2. **Input envelope.** `positions`/`bounds` must be 2-D real-valued
   sequences (numpy arrays or sequence-of-sequences). ndim ≥ 3 arrays
   compute something degenerate in the oracle (4-D broadcasts); they raise
   a pyo3 extraction `TypeError` here. Complex dtypes are outside the
   envelope. Both are recorded, not silently matched; no consumer has them.
3. **Malformed-input error texts** are replicated for the 0-D/1-D/list
   classes AND the inner-dimension classes (verified byte-for-byte against
   numpy 2.3.5: positions dims 0/≥3 → the broadcast `ValueError` text
   including its trailing space, bounds dims 0/1 → the `IndexError` text;
   positions dim 1 broadcasts `x → [x, x]` and bounds dims ≥3 are ignored —
   both compute bit-identically, pinned by parity cases); the exact
   `TypeError` text numpy's fancy indexing emits for ndim ≥ 3 inputs is
   not replicated (the oracle computes instead of raising there).

---

# Hypergraph factory — Verification

The hypergraph factory (`src/hypergraph_factory.rs`) is the Wave 4 Phase 4
leftovers slice's fourth migration: the `HypergraphFactory` pyclass (the
valid-nets filter, the ref→index mapping, the physics classification and the
per-net connection extraction) plus the `HypergraphBuildResult` pyclass,
ported from `temper_placer/extraction/hypergraph_factory.py` (the Python
module is now a wrapper: the `HypergraphFactory` shim class owns the scipy
COO assembly and the `netlist_to_hypergraph` convenience function stays
Python). Home crate: `temper-design-bundle` — the factory consumes the
`Netlist` contract pyclasses (`netlist_contracts.rs`), so the netlist reader
and the factory share one crate.

## Induction applicability

**Mathematical induction is not applicable to this module.** None of its
functions are recursive, and none iterate over a dimension whose
correctness depends on a size parameter:

- the valid-nets filter, the physics classification and the connection
  extraction are per-net constant-branch decisions (threshold compare,
  two-pin rule, HV/width classification) whose per-element operation is
  independent of the count and of the iteration order;
- the ref→index mapping is a per-component insert whose outcome (last
  duplicate ref wins) is fixed, not size-dependent;
- the per-net connection list is a bounded membership-filtered copy of the
  net's pins — the set collapse and its iteration order happen CPython-side
  (see the KTD9 boundary note below), by construction identical to the
  oracle's.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass
behaviour is bit-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/core/_hypergraph_factory_py_oracle.py`,
commit `58b302ce8`).

*Proof by structural cases.*

1. **The valid-nets filter.** The Rust side mirrors the oracle's loop
   exactly: a net survives iff `len(pins) >= 2` AND (not
   `ignore_global_nets` OR `len(pins) <= global_net_threshold`). The
   `pins` length is read through Python (`PyAny::len`), so non-list pins
   raise CPython's own `TypeError`; the `>` threshold comparison (in i64 —
   a NEGATIVE threshold filters every net, pinned by the negative-threshold
   differential case) and the `>= 2` rule are the oracle's exact predicates
   (the off-by-one boundary is pinned by the differential's custom-threshold
   case and the PBT selection property, and by the H1/H2 mutants).
2. **The ref→index mapping.** `node_ref_to_idx = {c.ref: i for i, c in
   enumerate(components)}` — a Rust `HashMap<String, usize>` with the same
   last-wins overwrite semantics (pinned by the duplicate-ref differential
   case and the H5 mutant). Ref strings extract losslessly; non-str refs
   are outside the documented envelope. `n_nodes` = `len(components)`
   (Python's own `len`).
3. **The physics classification.** `is_hv` uses CPython's own `==` on the
   stored `voltage_class`/`net_class` objects (`rich_compare`-based `.eq`),
   so the pyclass enum/str comparisons behave exactly as the oracle's
   `net.voltage_class == "HV"`. The width chain reproduces the oracle's
   branch order (net_class HighVoltage FIRST, then `max_current > 1.0`
   through CPython's `>`), with the constants 1.0/0.5/0.2 (0.2 is not
   representable in f32 — the cast is numpy's, so the stored double and the
   cast f32 both match the oracle's by construction; pinned by the
   float32-boundary differential case). `edge_voltages`/`edge_widths` are
   the exact 1.0/0.0 and 1.0/0.5/0.2 constants.
4. **The connection extraction.** Per valid net, the Rust side emits the
   connected component INDICES in PIN ORDER, membership-filtered through
   the ref→index map (`if comp_ref in node_ref_to_idx` — the oracle's exact
   predicate; the H6 mutant pinned it). The shim then builds
   `set(connected_indices)` — the identical construction the oracle
   performed (same members, same pin-order insertion) — so CPython's set
   iteration order, and therefore the COO triplet ORDER, is CPython's on
   both sides; the differential asserts `matrix.data/row/col` INCLUDING
   order (`test_matrix_triplet_order_is_cpython_set_order`,
   `test_duplicate_component_refs_last_wins`; the H10 pin-reversal mutant).
   `net.weight`/`net.max_current`/`net.name` pass through as the original
   Python objects — the Rust side never converts them, so int-vs-float
   leaves reach numpy and the PhysicsHypergraph untouched.
5. **Node weights.** `width * height` is Python's own `__mul__` on the
   original objects (int × int stays int; the H9 mutant pinned the
   operator), collected in component order.
6. **The assembly boundary (KTD9).** `np.array(..., dtype=np.float32)`
   casts and `coo_matrix((values, (rows, cols)), shape=...)` run in the
   shim on the Rust-returned objects — numpy/scipy conversion semantics
   (int leaves, 0.2's f32 rounding, empty-matrix handling, scipy's COO
   construction) are the libraries' own on both sides of the differential.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/core/test_hypergraph_factory_rust_differential.py`
  (18 tests; the RED state was demonstrated: the file fails to collect with
  `AttributeError: module 'temper_design_bundle_python' has no attribute
  'HypergraphFactory'` before the Rust pyclasses landed). Comparison keys:
  the COO matrix as `(shape, nnz, data-(dtype,shape,tobytes), row, col)` —
  triplet order included — plus every array as `(dtype, shape, tobytes())`.
  The 2026-08-05 adversarial addition: the negative-threshold case
  (`global_net_threshold=-5` filters EVERY net — RED before the fix: the
  `as usize` cast wrapped -5 to a huge threshold and filtered nothing).
- PBT (R1c): `test_hypergraph_factory_pbt.py` — 6 hypothesis properties
  (P1 edge-selection rule, P2 HV flag classification, P3 width
  classification with branch order, P4 incidence connectedness, P5 node
  weights, P6 hyperedge weights), each fail-capable.
- Metamorphic (R1d): `test_hypergraph_factory_pbt.py` — MR1 (net-order
  permutation: names/voltages/matrix columns follow the permutation;
  node_weights/node_refs invariant), MR2 (threshold monotonicity), MR3
  (pin-order permutation: the canonicalized matrix and all value arrays are
  invariant — the per-net triplet ORDER is CPython's and is the
  differential's domain, not a claim here), MR4 (ignore + threshold ≥
  max-pins ≡ no filtering).
- Anti-vacuity: 10 mutants, all caught by the differential/PBT suites:
  threshold `>`→`>=`, `>=2`→`>2` pins, HV flag `||`→`&&`, HV width branch
  dropped, ref map last-wins→first-wins (closed by the duplicate-ref
  differential case), connection membership check dropped (closed by the
  zero-components differential case `test_nets_without_components_parity`
  — nets whose refs match no component — plus the mixed-netlist cases and
  PBT P4; the earlier "UNKNOWN_REF case" attribution referred to no test
  in the suite and was corrected 2026-08-05), HV flag 1.0/0.0 swapped,
  0.5/0.2 widths swapped, node weights `*`→`+`, pin order reversed (caught
  by the triplet-order matrix comparison). **Re-verified 2026-08-05 with
  an explicit revert verification** (each mutant applied to the Rust
  source, the rebuilt extension run against the suites, the failure
  confirmed, the source restored, and `git diff` confirmed EMPTY before
  the next mutant): 10/10 caught. Full log in
  `docs/evidence/2026-08-05-wave4-phase4-leftovers-adversarial-fixes.md`.
- Rust practices (R1g): no `unwrap`/`expect` in non-test code; `PyResult`
  everywhere; `cargo clippy --release --features python` clean (0 warnings);
  borrow over clone (the net list is borrowed per iteration; only the
  emitted result holds owned handles).
- Performance A/B (R1b): the construction is O(components + pins) with no
  production consumers beyond the tests (the factory's only callers are
  `tests/core/test_hypergraph.py` and the extraction module re-export), so
  a `perf_ab` registration would measure a synthetic hot path. Per the
  plan's R2 this is the **"no regression beyond noise"** arm: the migrated
  factory performs the same per-net classification work plus one pyo3
  boundary crossing for the shim's assembly; no speedup is claimed. (No
  `perf_ab` registration — recorded, not skipped.)
- R1h (physics discipline): NOT APPLICABLE. The factory CLASSIFIES physics
  attributes (HV flags, current-based widths) onto a data structure that
  downstream heuristics consume; it encodes no CP-SAT constraint gating a
  physics quantity, computes no quantity a post-solve audit could recompute
  from placement coordinates, and feeds no solver. The R24
  Chebyshev/BMC/post-solve obligations have no referent.

## Documented deviations (per R1, recorded here)

1. **Ref-string envelope.** Component refs and net-pin refs must be `str`
   (the netlist contract's `ref` field is a str; every in-repo netlist uses
   str refs). A non-str ref raises a pyo3 extraction `TypeError` where the
   oracle would hash the object and compare by its own equality. Recorded,
   not silently matched; the differential and PBT suites use the netlist
   contract types exclusively.
2. **`HypergraphFactory` (the Python shim class) remains Python.** It owns
   the scipy/numpy assembly — the KTD9 boundary is the class boundary, not
   a method boundary. The pyclass underneath is the migrated compute.

---

# fields/* — R3 JUSTIFIED-KEEP record (Wave 4 Phase 4 leftovers slice)

The `temper_placer/fields/` tree (`field.py`, `interface.py`, `result.py` —
253 LOC) was assigned MIGRATE phase 4 in this ledger. Assessed 2026-08-05
under the Phase 4 leftovers slice, it is recorded **JUSTIFIED-KEEP** with
the named blocker below (the ledger entry carries the same text). No
migration was attempted: per D6, a named blocker outranks a phase row.

## The named blocker

**No portable compute.** Every operation in the tree is either a numpy
buffer operation or a passthrough over Python-owned objects; a migration
would produce a pyo3 wrapper whose every method calls back into Python —
the phase guide's measured net-negative boundary ("prefer surfaces whose
callers will also migrate — a Rust kernel behind a per-call marshalling
boundary can be net-negative").

Per module:

1. **`field.py` — `CostField`.** A frozen dataclass over a numpy-owned
   float32 grid. The only method, `to_flat()`, is
   `np.ascontiguousarray(grid.ravel()).astype(np.float32)` — three numpy
   buffer ops on a buffer Python owns. A pyclass would hold `Py<PyAny>`
   and call numpy back. The shape/height/width/total_cells properties are
   reads of `grid.shape`. No arithmetic, no control flow.
2. **`interface.py` — `CostFieldInput` / `FieldGate`.** `CostFieldInput`
   is a two-field frozen dataclass (no methods). `FieldGate` is an
   abstract extension point: `compute_field` raises `NotImplementedError`,
   `check` forwards to it, `to_delta` returns `None`. The concrete
   subclasses (thermal, congestion, ...) live in surfaces owned by other
   sessions (`router_v6/`, `physics/thermal_fdm.py`,
   `deterministic/state.py`) and subclass it in Python; migrating the base
   without migrating every subclass would churn their inheritance for zero
   compute value.
3. **`result.py` — `FieldResult` / `FieldNotReadyError`.** A frozen
   dataclass wrapping the `GateResult` pyclass (Phase 2) with a three-line
   fail-closed invariant (`__post_init__` compares `gate_result.status` to
   the `UNMEASURED` member — an identity comparison on the pyclass enum —
   and raises `ValueError`), four attribute-passthrough properties, and
   `to_cost_field_input()`, which is the `hasattr(self.field, "to_flat")`
   dispatch plus the same numpy buffer ops as `CostField.to_flat`. The
   invariant is real logic but operates on Python objects on both sides;
   the status comparison in Rust would be a `Py<PyAny>` getattr + identity
   check against a held instance — a boundary with no algorithm to
   protect.

## Re-decidable when

A consumer of these types migrates and carries the arithmetic with it (the
phase guide's rule: migrate the kernel, keep the boundary); or the numpy
buffer boundary is replaced by a typed buffer protocol the Rust side can
own. At that point the ledger entry's blocker no longer holds and the
surface can be re-assessed.

## Evidence recorded (unchanged surface)

The existing suites pin the current behavior:
`tests/fields/test_field_result.py` and
`tests/fields/test_fieldresult_invariants_pbt.py` (52 + property tests,
all green on the current branch). The tree was NOT modified by this slice.
