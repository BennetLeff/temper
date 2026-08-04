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

# PCL tag-dispatch + parse layer — Verification

Wave 4, Phase 2 (the contracts-as-pyo3-pyclasses pivot). Sources:
`packages/temper-design-bundle/src/pcl_tags.rs` and `.../pcl_parse.rs`,
porting `temper_placer/pcl/tag_dispatch.py` and
`temper_placer/pcl/_parse_utils.py`.

## Candidate scorecard (why temper-design-bundle, not temper-pcl-ir)

`docs/wave4-verdicts.yaml` records "PCL constraints are contract objects;
temper-pcl-ir is the Rust seed." That names the right *IR vocabulary* but not
a viable pyclass host, and the port went to `temper-design-bundle` instead.
The reasoning, stated as a crate-selection verdict:

| crate | pyo3 today | verdict |
|---|---|---|
| **temper-design-bundle** | yes (`python` feature, `temper_design_bundle_python`) | **CHOSEN** |
| temper-pcl-ir | no | rejected — see below |
| temper-constraints | yes | rejected — heavier deps, wrong layer |
| temper-drc-rs / temper-rust-router | yes | rejected — unrelated surface |

- **temper-pcl-ir is a pure `serde` data crate with no pyo3 at all**, and it
  is consumed as an *rlib* by both `temper-design-bundle` and
  `temper-constraints`. Adding `pyo3 = { features = ["extension-module"] }`
  to it would push extension-module linkage into every consumer — including a
  crate that already builds its own extension module. It stays the shared IR
  vocabulary (`ConstraintTier`, `PclConstraintKind`, merge order), which is
  exactly what the verdict line is about, and `temper-design-bundle` already
  depends on it.
- **temper-design-bundle is the established Phase-2 host.** `net_types.rs`,
  `loops.rs`, `design_rules.rs`, `gates.rs` and `priority.rs` already live
  there, and `temper_placer/core/*.py` are already pure-delegation shims to
  it. It also already carries `pcl.rs` (the PCL document → IR reader), so the
  PCL surface has a home there rather than a new one.
- **No heavy C++ anywhere on this path.** temper-design-bundle's tree is
  serde / serde_json / serde_yaml / sha2 / thiserror / pyo3 — no C++
  toolchain, no OpenCV, no OR-Tools. (`temper-constraints` would have added
  nalgebra + rayon for a layer that needs neither.)

## What moved, and what deliberately did not

**Moved to Rust.** The tag-expression algebra as `#[pyclass(frozen)]`
contract objects (`TagRef`, `TagAnd`, `TagOr`, `TagNot`, `ComponentRef`); the
Floyd-Warshall transitive closure; the `ComponentTag.__le__` relation;
`resolve` / `components` / `_tag_to_component_refs`;
`_check_overconstrained`; and all six `_parse_utils` functions.

**Deliberately not moved, with reasons:**

- **`ComponentTag` stays a Python `enum.Enum`.** Production code does
  `for t in ComponentTag` (`_tag_parser.py`, building the "valid tags"
  warning) and `ComponentTag(value)`. A pyo3 `#[pyclass]` enum supports
  neither — class-level iteration requires a *metaclass* `__iter__` and pyo3
  exposes no metaclass hook (the same limitation the `priority` migration had
  to document as a deviation). Migrating it would be a public API change,
  which this task forbids. Rust holds the lattice as indices and returns the
  live Python singletons at the boundary; the differential asserts `is`
  identity, not equality.
- **`PCLParseError` and the five PCL enums stay Python classes**, for the
  same reason plus exception identity: `except PCLParseError` binds a class
  object, and Rust raises *that* object rather than a look-alike.
- **`E()` and `pre_expansion_validate()` stay Python.** Both are
  `hasattr`/`dir()`-driven reflection over arbitrary duck-typed constraint
  objects. A Rust port would be one FFI hop per attribute probe — strictly
  slower and strictly more fragile. The compute they call into is what moved.

## Induction applicability

Two inductive arguments are load-bearing here.

**(1) `resolve` terminates and is correct by structural induction on the
expression tree.** The tree is finite and acyclic by construction: every node
is built by a `#[new]` that takes already-constructed children, so no node can
reach itself. Induction over tree height `h`:

- *Base (h = 0).* `TagRef` and `ComponentRef` are leaves. `TagRef` answers
  from two finite loops over `comp.tags`; `ComponentRef` is one `==`. Both
  terminate and match the reference's leaf branches line for line.
- *Step.* `TagNot(e)` = `!resolve(e)`, `TagAnd(l, r)` = `resolve(l) &&
  resolve(r)`, `TagOr(l, r)` = `resolve(l) || resolve(r)`, each with height
  strictly less than `h`. Rust's `&&`/`||` short-circuit exactly as Python's
  `and`/`or` do, so even the *number of child evaluations* matches — which
  matters because a child can raise (`TypeError` from a non-ComponentTag
  `TagRef`), and short-circuiting decides whether that raise is reached.
- *Foreign nodes.* A value matching none of the five pyclasses falls to
  `Ok(false)`, reproducing the reference's trailing `return False` rather than
  raising.

**(2) The Floyd-Warshall closure is the reflexive-transitive closure of the
parent relation.** Standard loop invariant: after outer iteration `k`,
`closure[i][j]` is true iff `j` is reachable from `i` using only intermediates
drawn from `{0..k}`. Seeding sets `closure[i][i]` (reflexivity) and every
direct parent edge; at `k = n` the intermediate set is unrestricted, so the
relation is the full reachability closure. The Rust keeps the same `k, i, j`
loop order and the same relaxation predicate as the Python, over a `u16`
bitmask instead of a `Vec<Vec<bool>>` — a representation change, not an
algorithm change. The lattice properties this implies are asserted directly as
Rust unit tests (`closure_is_reflexive`, `closure_is_transitive`,
`closure_is_antisymmetric_so_the_order_is_partial_not_merely_a_preorder`,
`every_tag_reaches_all_and_all_reaches_only_itself`), and — because 14 tags is
small — the full 14x14x14 triple is checked **exhaustively**, not sampled.
That is a proof by exhaustion over the entire input domain of the relation,
not a property test.

The parse layer has no recursion and no iteration whose length depends on a
computed value, so induction does not apply there; the structural argument
below carries it.

## Structural proof

**Order sensitivity — the part most likely to be got wrong.** The reference
reads a `set` in two places, and CPython set iteration order depends on
`PYTHONHASHSEED`.

1. `resolve`'s `for ct_str in comp.tags`. The body has no side effects and
   only ever `return True`; the function otherwise falls through to `False`.
   So the result is `∃t ∈ tags . lower(t) ∈ ComponentTag ∧ t ≤ expr.tag` — an
   existential quantifier over a set, which is order-invariant by definition.
   Made an explicit input and checked over every permutation in
   `test_resolve_is_invariant_to_the_tag_frozensets_iteration_order`.
2. `_check_overconstrained`'s `set(adjacency) & set(separation)`. Here the
   order **is** observable: the function raises on the first offending pair,
   so which message you get depends on the seed. Sorting the keys would make
   the port deterministic and therefore *different* — precisely the
   undetectable behaviour change this program warns about. The port instead
   builds the same CPython `set` objects and iterates the same `__and__`
   result, so the live order is passed through rather than replicated.
   Mutation **M21** (sort the intersection) is the guard, and it is only
   killed by a case with enough keys that sorted order and set order diverge —
   twelve, in `test_M21_the_set_intersection_is_not_sorted`.

**Bit-exactness classes newly catalogued by this migration:**

- **B13 — `str.isdigit()` is not `char::is_ascii_digit()`.** CPython's
  `isdigit` is true for fullwidth `'１'`, Arabic-Indic `'٣'` and superscript
  `'²'`. `'１０mm'` parses to `10.0`. `py_isdigit` decides ASCII locally and
  delegates everything else to CPython, so it cannot drift with a Unicode
  version bump. (Mutation M01.)
- **B14 — CPython's ASCII whitespace set is larger than Rust's.**
  `str.strip()` removes `\x1c`–`\x1f` (the C0 file/group/record/unit
  separators); Rust's `char::is_whitespace` does not, because they are not in
  the Unicode `White_Space` property. `'\x1c5\x1c'` parses to `5.0`.
  (Mutation M02, plus a Rust unit test asserting the exact ASCII set.)
- **B15 — `float(s)` accepts more than `str::parse::<f64>`.** Unicode digits
  and PEP-515 underscores. Underscores cannot survive the scanner, Unicode
  digits can; `py_float` therefore restricts the Rust fast path to
  `[0-9.-]`-only ASCII, where both parsers are correctly rounded and therefore
  agree by construction, and delegates everything else.
- **B16 — Unicode case mapping is not a bijection, and the reference relies on
  it.** `'sıgnal'.upper() == 'SIGNAL'` but `'sıgnal'.lower() != 'signal'`, so
  `resolve`'s uppercase membership test is *not* redundant with its lowercase
  hierarchy walk. This is what makes mutation M15 killable at all.
- **B17 — `x * 10.0` and `x / 0.1` are not the same function.** They agree on
  every integer centimetre value (which is why M30 survived a corpus built
  from integers) and disagree at e.g. 28.3475, 445.3872, 228.7622. The port
  multiplies, as the reference does.

**R24 (physical quantities).** `_parse_distance_with_unit` returns
millimetres. The three conversion factors are the exact decimal doubles the
Python used — `0.0254` (mm/mil), `25.4` (mm/in), `10.0` (mm/cm) — asserted by
*bit pattern* in
`pcl_parse.rs::unit_factors_are_the_exact_decimal_doubles_python_used`, and
each conversion is a single correctly-rounded multiply on both sides with no
reassociation and no fused multiply-add. Mutations M03 (wrong mil factor), M04
(wrong inch factor) and M30 (divide instead of multiply) are all killed.

**Frozen-dataclass fidelity.** `__repr__` (field names included, values via
Python `repr()`), `__eq__` (exact-type check then per-field Python `==`;
foreign types answer `False`, never raise), `__hash__` (CPython's own tuple
hash over a real tuple — not a replicated xxPRIME), `__setattr__` /
`__delattr__` (`dataclasses.FrozenInstanceError` with CPython's two distinct
message forms), `copy.deepcopy` and `pickle` (via `__reduce__`, which
`ConstraintCollection.copy()` exercises on the live path), and
`__match_args__`. Each is asserted against the oracle, and each has a mutation
(M25, M28, M26, M27).

## Documented deviations (per R1, recorded here)

- **`dataclasses.fields()` no longer works** on
  `TagRef`/`TagAnd`/`TagOr`/`TagNot`/`ComponentRef` — they are pyclasses, not
  dataclasses. Verified 2026-08-04 that no consumer calls it: no
  `dataclasses.fields`, `asdict`, `astuple` or `dataclasses.replace` against
  these types anywhere in `packages/temper-placer/src`, `tests/` or
  `scripts/`. `__match_args__` is provided so structural pattern matching
  still works.
- **`__repr__` of the five node types is reproduced exactly**, including for
  the duck-typed field values the frozen dataclass also accepted.

## Evidence

- **Differential (R1a/R1f, TDD red→green):**
  `packages/temper-placer/tests/pcl/test_parse_utils_rust_differential.py`
  (oracle `_parse_utils_py_oracle.py`) and
  `.../test_tag_dispatch_rust_differential.py` (oracle
  `_tag_dispatch_py_oracle.py`), both pinned verbatim at commit `5a17025b1`.
  ~900 assertions. Comparison is by type-carrying signature
  (`tests/pcl/_pclsig.py`): `float.hex()` per float, concrete type name per
  non-float leaf, enum members by owning class + member name, exceptions by
  class qualname + exact message. **No tolerance anywhere.**
- **Comparator self-test (anti-vacuity on the gate itself):**
  `tests/pcl/test_pclsig_selftest.py`, 19 tests proving the comparator
  distinguishes f32/f64, int/float, `True`/`1`, `0.0`/`-0.0` and 1 ulp — and
  that it *identifies* genuinely equal values. It found a real gap during
  development: `float.hex()` renders both NaN signs as `'nan'`, so the
  comparator now reads the sign bit via `math.copysign`.
- **PBT (R1c):** `tests/pcl/test_pcl_rust_pbt.py` — 7 properties (P1–P7)
  covering well-formed and arbitrary parse input, all five enum parsers,
  random expression trees, the netlist sweep including result order, the
  partial-order laws, and pyclass repr/eq/hash.
- **Metamorphic (R1d):** same file — M1 double negation, M2 De Morgan, M3 tag
  refinement narrows-never-widens, M4 monotonicity under tag addition
  (negation-free), M5 unit-suffix case invariance, M6 whitespace invariance,
  M7 unit-less == millimetres.
- **Relations that do NOT hold, pinned with witnesses** rather than narrowed
  away (`TestRelationsThatDoNotHold`): W1 `n in != n*1000 mil` (witnesses
  n = 3, 6, 12, 24, 29, 48); W2 monotonicity fails under negation; W3 the
  negative-sign rule is not uniform (`'-5'` accepted, `'-5mm'` rejected);
  W4 `'²'.isdigit()` is True but `float('²')` raises; W5 scientific notation
  is not accepted at all (found by M5/M6/M7 failing on generated floats whose
  `repr` carries an exponent).
- **Mutation corpus (anti-vacuity, R1 mandatory):**
  `packages/temper-design-bundle/mutation_corpus_pcl.py`, 30 mutations,
  results in `mutation_corpus_pcl_results.json`. **29 killed, 1 survivor
  proven equivalent.** Every mutation is applied to the real source, rebuilt,
  and run against the gate suite; the harness verifies the unmutated tree is
  GREEN before starting and after restoring.
  - First run: 22/27 killed, 4 survivors (M10, M15, M23, M26). M15, M23 and
    M26 were closed by *new discriminating tests*
    (`test_M15_uppercase_membership_is_not_redundant_with_the_hierarchy_walk`,
    `test_M23_product_nesting_determines_which_contradiction_is_reported`,
    `test_M26_hash_distinguishes_distinct_nodes_exactly_as_the_dataclass_did`).
    Three further mutations (M28–M30) were then added; M21 was found to
    survive and was closed by `test_M21_the_set_intersection_is_not_sorted`.
  - **M10 (`"mm" | ""` → `"mm"`) is a proven-equivalent mutant**, not an
    unclosed survivor. `value` is stripped before the scan, so its last
    character is not whitespace; `unit_str = value[i:].strip().lower()` is
    empty only if `value[i:]` is entirely whitespace, but `value[i:]` is
    non-empty and ends with `value[-1]`. Contradiction — the arm is
    unreachable. Backed empirically by an exhaustive search over all 69,904
    strings of length ≤ 4 from `" \t\x1c.-0123456789ax"`, re-run inside
    `test_M10_the_empty_unit_arm_is_provably_unreachable` so it cannot rot.
  - The harness itself carries a fix worth noting: restoring a mutated file
    with `shutil.copy2` preserves the *source* mtime, so cargo's mtime-based
    staleness check skipped the rebuild and left a mutated `.so` behind a
    clean tree. That produced a bogus `hash() == 0` in a later test session.
    The restore now writes bytes, forcing a fresh mtime.
- **Rust unit tests:** 49 in-crate tests, including the exhaustive lattice
  proofs, the exact CPython ASCII-whitespace set, and the R24 factor bit
  patterns.
- **Performance A/B (R1b):** `benchmarks/perf_ab.py`, stages
  `pcl-tag-dispatch/tag_resolve_sweep` and
  `pcl-parse-utils/parse_distance_batch`. Both arms assert parity in-harness
  before timing. Release, darwin/arm64, 400-component netlist × 8 expressions:
  ratio **0.465** (2.15× faster) for the tag sweep and **0.421** (2.37×
  faster) for the parse batch.
  - The #714 lesson is enforced structurally: both the benchmark and
    `tests/pcl/test_pcl_bench_fixture_parity.py` import the *same*
    `tests/pcl/_pcl_bench_fixture.py`, so the benchmark cannot reach an input
    the differential has not already compared. Neither kernel accumulates
    across iterations, so there is no iterative float divergence to compound.

## Not verified (stated, not claimed)

- **Linux.** Every measurement here is darwin/arm64. The PCL kernels make no
  libm calls — `resolve` is a boolean tree walk and the unit conversion is a
  single IEEE-754 multiply by a decimal double that is exactly representable
  identically in both languages — so there is no transcendental surface for
  Linux and macOS libm to differ on. That is the argument; it is not a
  measurement.
- **Perf-gate baselines.** The two new `_BENCHMARKS` keys have **no row** in
  `power_pcb_dataset/metrics/perf_ab_baseline.jsonl` and therefore fail the
  gate closed. That is deliberate: `perf_ab.py`'s own documented procedure
  requires capturing baselines on CI (linux/x86_64), because a
  darwin-captured row carries a measured ~-11% platform bias that would make
  the gate miss every regression between +20% and +35%. No baseline file was
  edited.
- **`pcl/constraints.py` `__repr__` is already non-deterministic**, and this
  migration does not touch it. `BaseConstraint` is a `@dataclass` whose
  `constraint_type` field is a `ConstraintType` enum member carrying
  `frozenset`s of other enum members; `repr()` renders those frozensets in
  identity-hash order, so `repr(AdjacentConstraint(...))` differs between
  processes (measured: three runs produced three different orderings).
  A future phase that turns those into pyclasses cannot preserve that repr,
  because it is not a function of the value. Recorded here so the next phase
  does not discover it late.
- **`BaseConstraint.__eq__` ignores every subclass field.** The `@dataclass`
  decorator is only on the base, so `AdjacentConstraint(a='Q1', b='Q2',
  max_distance_mm=10.0, id='x') == AdjacentConstraint(a='R1', b='R2',
  max_distance_mm=99.0, id='x')` is `True` (measured). Also out of scope here,
  also recorded for the next phase.
