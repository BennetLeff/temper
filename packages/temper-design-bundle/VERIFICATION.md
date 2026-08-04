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

Three third-party/stdlib surfaces are called back across the pyo3 boundary
rather than reimplemented. Each is a correctness decision with a named
divergence that reimplementation would have introduced:

| Kept | Why keeping it is the correct call |
|------|------------------------------------|
| `yaml.safe_load` (the tokenizer) | PyYAML implements YAML **1.1**, `serde_yaml` implements YAML **1.2**. They disagree on inputs these files can contain: `on`/`off`/`yes` are booleans under 1.1 and strings under 1.2; `012` is octal `10` under 1.1 and decimal `12` under 1.2; `1_000` is the integer 1000 under 1.1 and a string under 1.2. Re-tokenizing would have *changed behaviour* while the differential on the shipped fixtures stayed green. Pinned by `test_load_loop_template_yaml_11_booleans_parity`, which asserts the 1.1 resolution is in force so the test cannot pass vacuously. |
| `pathlib.Path.glob` + `sorted` | `PurePath` ordering and glob pattern semantics (hidden files, `**`, character classes) are intricate and version-sensitive; delegating makes `load_loop_collection`'s traversal order exact by construction. Pinned by `test_load_loop_collection_ordering_parity` / `..._pattern_parity`. |
| `yaml.dump` (the emitter) | The emitted BYTES are the contract (`save_loop_to_yaml` output is re-read by the loader and by humans). PyYAML's emitter carries its own float representer (`repr(x).lower()` plus the `.0e` fixup) and scalar-quoting rules; a Rust emitter would have produced different, equally-valid YAML. Pinned by `test_save_loop_to_yaml_byte_identical` (byte-for-byte, 7 branch-covering loops). |

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
cause chaining, and the emitter's field-selection logic.

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

7. **`save_loop_to_yaml`.** The emitted mapping is built in the oracle's
   insertion order (`sort_keys=False` makes insertion order the emitted key
   order), with the oracle's exact conditionals: truthiness for
   `components`/`pins`/`nets`/`net`/`return_layer`/`return_net`, and `is not
   None` for the six event fields — the distinction that keeps a `0.0` slew
   rate alive. `path.parent.mkdir(parents=True, exist_ok=True)` and
   `yaml.dump(..., default_flow_style=False, sort_keys=False,
   allow_unicode=True)` are the same calls, so the output is byte-identical
   by construction and asserted so.

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
- **`NetClassRulesDict` is a pyclass, not a dataclass.** Attribute surface,
  mutability, `__eq__` and `__repr__` are preserved;
  `dataclasses.fields()` / `dataclasses.asdict()` / `dataclasses.replace()`
  no longer apply. No consumer uses them (verified 2026-08-04).
- **Argument-type-check precedence.** `source`, `pattern`, `name` and
  `description` are typed `String` at the pyo3 boundary, so a non-`str`
  argument raises `TypeError` with the identical pyo3 message but *before*
  the body runs — where the oracle would have raised its own `LoopLoadError`
  first if `data` was also invalid. Message identical, precedence different.
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
  `packages/temper-placer/tests/io/test_loaders_rust_differential.py` — 168
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
  mutations of `loaders.rs` were built and run; each was caught, and
  reverting restored 163/163 green:

  | Mutant | Change | Caught by |
  |--------|--------|-----------|
  | A | drop `sorted()` on class-pair keys | 4 tests — `test_netclass_real_fixture_bit_identical`, `..._class_pairs_exact`, `test_netclass_crafted_yaml_bit_identical[pair_key_sorting, pair_key_arity]` |
  | B | emitter uses truthiness instead of `is not None` for events | 2 tests — `test_save_loop_to_yaml_byte_identical[zero_valued_events]`, `..._round_trip_parity[zero_valued_events]` |
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
- **Performance A/B (R1b):** `temper_placer.profiling.pipeline_metrics::
  profile_loaders`, wired into `temper profile run --module loaders|all` and
  emitting `module="loaders"`, `stage="loaders"`, metrics
  `netclass_load_ms` / `loop_collection_load_ms` / `total_ms` — the shape
  `scripts/pr_perf_compare.py` compares against the rolling main-branch
  median under `TIMING_MARGIN = 0.20`. These loaders are I/O-bound YAML
  parsing with no compute kernel, so per the program's R2 this is the
  "no regression beyond noise" arm, NOT a speedup claim. The gate is
  **wired but not yet enforcing**: the Phase-0 hard-gate wiring (#681) has
  not merged, so `pr-perf-check.yml` still carries `continue-on-error: true`.
  It bites the moment #681 lands, with no further change here.
- **R1h (physics discipline): NOT APPLICABLE.** These are data/format
  loaders. They perform no physics, encode no geometric constraint, and
  compute no value that a post-solve audit could recompute from coordinates —
  the single arithmetic operation in either module is `float(...)` coercion.
  The R24 Chebyshev-soundness / BMC-exhaustive / post-solve-audit obligations
  have no referent here.
- **Consumer suites run unchanged against the migrated loaders:**
  `tests/io/` (480 passed, 12 skipped, 1 xfailed), `tests/core` + `tests/pcl`
  (932 passed), `tests/io/test_netclass_loader.py`,
  `tests/io/test_loop_loader.py`, `tests/core/test_design_rules_field_parity.py`,
  `tests/router_v6/test_layer_assignment_ssot.py`,
  `tests/router_v6/test_phase1_anti_false_zero.py`.
