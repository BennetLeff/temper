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

## Evidence

- Differential (R1a/R1f, TDD red→green): 214 assertions across
  `packages/temper-placer/tests/core/test_board_rust_differential.py`
  (oracle `_board_py_oracle.py`, commit `5a17025b1`) and
  `test_netlist_rust_differential.py` (oracle `_netlist_py_oracle.py`,
  commit `e799183c4`). RED first: both files failed to collect
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
  diagonal if the dedup were dropped).
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
||||||| parent of 6dc58d6bc (feat(wave4): Phase 3 candidate 3 — the KiCad parse engine to Rust)



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
  in order. 42 assertions + the M8 discriminating fixture (net-0 trace) pass.
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
