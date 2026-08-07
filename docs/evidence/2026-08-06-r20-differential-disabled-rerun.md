<!-- provenance: commit=56beab62ef1885ad08405f8d54428cd199651fc1 dirty=false branch=perf/r20-differential-disabled
     base=56beab62e (origin/main at run time) date=2026-08-06 method=R20 campaign re-run with differential disabled
     (suites-only: PBT + MR + in-crate Rust unit tests + non-differential pytest unit files; every
     `*_rust_differential.py` excluded from the run). Drivers (outside the repo, per the
     script-manifest-gate precedent): /tmp/wt9-r20_r20_driver.py (campaign) +
     /tmp/r20_attribution_isolated.py (per-mutant isolated attribution for every
     suites-only KILL). Repo discipline: exit-1-only kills, pristine source revert per
     mutant, isolated .so state per mutant, pristine rebuild + full-suite green at the end. -->

# R20 differential-disabled re-run — which differentials can be removed (issue #834)

**Task.** Per the R20 criterion (deprecation-eligibility audit
`docs/evidence/2026-08-06-deprecation-eligibility-audit.md` §3 / PR #830), a
differential (`test_*_rust_differential.py`) may be removed only when the
**property (PBT), metamorphic (MR) and unit-test suites** catch every mutant
the campaign caught. This run re-executes the four sampled modules' mutation
campaigns with the differential **disabled** (excluded from the run) and
counts survivors. **No production code was changed** — the differential
disablement was run-time test selection, not a committed edit.

**Suites-only run definition.** For each module the campaign was re-run
against: (1) the standalone `*_pbt.py` files, (2) the in-crate Rust
`#[test]` units (`cargo test -p <crate>`) where the target file carries unit
tests, and (3) the non-differential pytest unit files that exercise the
migrated surface (e.g. `tests/validation/test_trace_analyzer.py`,
`tests/io/test_config_validation.py`, `test_seed_filter_config.py`). Every
`*_rust_differential.py` file was excluded. `test_prop*`/`test_mr*` tests
that live *inside* a differential file were excluded with it. A mutant
counts **KILLED** only on a pytest exit 1 or a Rust unit-test failure; exit 0
is **SURVIVED**; a build/collection failure is **INFRA** and never counts as
a kill. Every mutant was reverted immediately; the campaign ended with a
pristine rebuild of all four crates and a green full-suite (differential +
suites-only) run (103+171+141+106+25+454 = 1000 tests), `git diff` empty.

## Headline

| Module | Campaign mutants | Survivors with differential disabled | Verdict |
|---|---|---|---|
| priority (temper-design-bundle) | 3 (repr/default surface) | **3 / 3** | **RETAIN** |
| constraints (temper-constraint-compiler) | 10 (M9 provably-equivalent excluded) | **5 / 10** | **RETAIN** |
| drc validation slice (temper-drc-rs) | 12 | **10 / 12** | **RETAIN** |
| drc contracts (temper-drc-rs) | 11 | **11 / 11** | **RETAIN** |
| drc clearance validator (temper-drc-rs) | 5 | **4 / 5** | **RETAIN** |
| loaders (temper-design-bundle + temper-io-types) | 10 | **3 / 10** | **RETAIN** |

**4/4 modules RETAIN — the audit's verdict is confirmed.** But its
per-mutant attribution is substantially wrong: the full re-run found suites
coverage the sampling missed in **12 of 51** mutants, and two of the audit's
three "PBT genuinely covers" claims (loaders M9) and several of its
"differential-only" claims do not survive the actual run. The verdict holds
because every module still has ≥ 3 mutants that the suites cannot catch.

---

## 1. priority (`core/priority` → `temper-design-bundle/src/priority.rs`)

Suites-only: `tests/core/test_priority_pbt.py` (P1–P5 + MR1–MR4 + vacuity
guards) + `cargo test -p temper-design-bundle` (priority unit tests
`py_repr_tests`, `kw_boundary_tests`). Differential disabled:
`test_priority_rust_differential.py`. The PBT/MR surface pins classification
outcomes and the `(name, value)` tables; nothing asserts enum `repr` text,
dataclass defaults, or dataclass `repr` byte-for-byte.

| Mutant | Suites-only outcome | Differential-only discriminating assertion |
|---|---|---|
| PR1 enum member repr rendering changed | **SURVIVES** | `test_priority_rust_differential.py::test_enum_str_and_repr_identical` — `repr(rust_member) == repr(py_member)` |
| PR2 `PlacementPhaseConfig.max_distance_mm` default 20.0 → 25.0 | **SURVIVES** | `::test_placement_phase_defaults_identical` — default-constructor field parity |
| PR3 `RoutingPhaseConfig.allow_layer_change` default true → false | **SURVIVES** | `::test_routing_phase_defaults_and_round_trip_identical` |

**Verdict: RETAIN** (3/3 survive). Audit prediction **confirmed exactly**.

---

## 2. constraints (temper-constraint-compiler: builder/compiler/reporter)

Suites-only: `test_{builder,compiler,reporter}_pbt.py` + `test_{builder,compiler,reporter}.py`
+ `test_existing_constraint_integration.py` + `cargo test -p temper-constraint-compiler`
(70 in-crate unit tests incl. `neumaier_matches_cpython_sum`,
`find_similar_prefix_and_suffix`). Differentials disabled: all three.

| Mutant | Suites-only outcome | Catching test / differential-only assertion |
|---|---|---|
| M1 filter spacing `dist < min` → `<=` | **KILLED** | `test_existing_constraint_integration.py::TestComponentSpacingRuleIntegration::test_hard_spacing_rule_rejects_close_slots` — `filter((15.0,0.0)) is True` at `min_separation_mm=15.0` (exact boundary) |
| M2 filter proximity `dist > max` → `>=` | **KILLED** | `test_existing_constraint_integration.py::TestProximityRuleIntegration::test_hard_proximity_rule_rejects_far_slots` — `filter((8.0,0.0)) is True` at `max_distance_mm=8.0` |
| M3 escape None-clearance default 3.0 → 0.0 | **SURVIVES** | `test_compiler_rust_differential.py::test_escape_none_clearance_default_three_mm` — 2.0mm inside / 4.0mm outside the 3.0 default |
| M4 Neumaier → naive sum | **KILLED** (unit test) | `cargo test`: `constraints::mod::tests::neumaier_matches_cpython_sum` (`sum([1e16,1.0,-1e16]) == 1.0`; naive gives 0.0) |
| M5 message threshold `py_float_str` → `{:.1}` | **SURVIVES** | `test_reporter_rust_differential.py::test_spacing_message_multi_decimal_threshold` — `"< 10.25mm"` vs `"< 10.2mm"` |
| M6 corridor `d < half` → `<=` | **SURVIVES** | `::test_corridor_check_exact_half_width_clear` |
| M7 `_find_similar` min-length-2 guard dropped | **KILLED** (unit test) | `cargo test`: `constraints::validate::tests::find_similar_prefix_and_suffix` |
| M8 builder zone empty-string gate dropped | **SURVIVES** | builder differential `zone=""` yields no error |
| M10 proximity penalty multiplier 10.0 → 5.0 | **SURVIVES** | random-scorer differential parity |
| M11 spacing check `dist >= min` → `>` | **KILLED** | `test_reporter_pbt.py::test_p3_spacing_satisfied_iff_distance_ge_threshold` — hypothesis samples `dist == min_sep` (the floats strategy generates exact values, e.g. 10.0) |

**Verdict: RETAIN** (5/10 survive: M3, M5, M6, M8, M10). **Audit refuted on
5 mutants** — M1/M2/M11 were predicted differential-only but are killed by
exact-boundary assertions in `test_existing_constraint_integration.py` and
the reporter PBT (which the audit said "almost never" hits equality; the
hypothesis floats strategy generates exact boundary values), and M4/M7 are
killed by in-crate Rust unit tests the audit attributed to the differential.

---

## 3. drc checks (temper-drc-rs)

Suites-only:
- validation slice: `test_drc.py` + `test_drc_runner.py` +
  `test_trace_analyzer.py` (the only non-differential pytest files that
  exercise the `validation.rs` kernels; the `*_pbt.py`-style coverage lives
  inside the differential files). `validation.rs` carries zero `#[test]`.
- drc_contracts: `test_report_pbt.py` + `test_drc.py` + `test_drc_runner.py`.
  `drc_contracts.rs` carries zero `#[test]`.
- clearance: `test_clearance_validator_pbt.py`. `req_safe_01.rs` carries
  zero `#[test]`.

### 3a validation slice (`validation.rs`, 12 mutants)

| Mutant | Suites-only outcome | Catching test / differential-only assertion |
|---|---|---|
| M1 `infer_package_type` drops `"dip"` | **SURVIVES** | `test_drc_oracle_rust_differential.py` deterministic `DIP-8 → tht` case |
| M2 `tht_hole_collisions` `:.3` → `:.2` | **SURVIVES** | `test_tht_check_rust_differential.py` message-format comparisons |
| M3 `tht_hole_collisions` drops `+ min_clearance` | **SURVIVES** | `test_tht_check_rust_differential.py` |
| M4 `trace_length` net filter `==` → `!=` | **KILLED** | `test_trace_analyzer.py::test_trace_length` (`approx(20.0)` under the inverted filter) |
| M5 `min_hv_lv_trace_clearance` `min` → `max` | **KILLED** | `test_trace_analyzer.py::test_hv_lv_trace_clearance` (`approx(20.0)`; max fold gives √500 ≈ 22.36) |
| M6 overlap severity `>5.0` → `>50.0` | **SURVIVES** | `test_geometric_rust_differential.py` CRITICAL-classification case |
| M7 boundary flag `>0.0` → `>1e9` | **SURVIVES** | `test_geometric_rust_differential.py` |
| M8 default severity `warning` → `error` | **SURVIVES** | `test_drc_rust_differential.py` |
| M9 penalty default weight 1.0 → 0.0 | **SURVIVES** | `test_drc_rust_differential.py` |
| M10 group sort removed | **SURVIVES** | `test_drc_oracle_rust_differential.py` sorted-order assertions |
| M11 fingerprint separator `,` → `;` | **SURVIVES** | `test_drc_fence_rust_differential.py` |
| M12 `"erc"` arm increments `drc` | **SURVIVES** | `test_drc_fence_rust_differential.py` |

### 3b drc_contracts (`drc_contracts.rs`, 11 mutants) — **all SURVIVE**

M1 WARNING weight, M2 `info_count`, M3 fail-closed `passed`, M4 merge
later-metrics-wins, M5 `Location.__repr__` layer, M6 `Issue.__str__`
truncation, M7 bounds sign flip, M8 `get_clearance` always 0.0, M9
`from_dict` rotation default, M10 penalty `2*w`, M11 `members()` order — all
**SURVIVE** the suites-only run. The report PBT draws a random severity via
`rng.choice(Severity.members())`, so even M11 (order swap) does not change
any rendered output. Discriminating assertions: all 11 live inside
`test_drc_contracts_rust_differential.py`
(`test_prop1_severity_weight_table`, `test_prop2_run_result_passed_fail_closed`,
`test_mr1_merge_is_order_preserving_concatenation`,
`test_consumer_{to_dict_and_json,location_issue_str,geometry_accessors,constraint_set_methods,from_dict_to_dict_roundtrip}_identical`,
`test_construction_field_repr_str_identical`, `test_severity_surface_identical`,
`test_prop3_error_count_is_recomputed`, `test_prop4_penalty_is_severity_weighted_sum`).

### 3c clearance validator (`req_safe_01.rs`, 5 mutants)

| Mutant | Suites-only outcome | Catching test / differential-only assertion |
|---|---|---|
| M9 same-domain pairing killed | **SURVIVES** | `test_clearance_validator_rust_differential.py::test_same_domain_functional_pairing` |
| M10 copper distance biased +1e-9 | **KILLED** | `test_clearance_validator_pbt.py::test_prop_measured_mm_is_actual_copper_gap` — the PBT independently recomputes the copper gap and compares against `measured_mm` |
| M11 report sort reversed | **SURVIVES** | `::test_report_sorted_worst_first` |
| M12 IEC `min_clr` halved | **SURVIVES** | `::test_verify_identical` / `::test_matrix_values_pinned` |
| M13 origin-modelled WARNING clause dropped | **SURVIVES** | `::test_verify_stats_components_and_rows` WARNING-record comparison |

**Verdict: RETAIN** (25/28 drc mutants survive). **Audit refuted on 3** — drc
validation M4/M5 are killed by `test_trace_analyzer.py` (a plain unit test
that delegates to the Rust kernels), and clearance M10 is killed by the
clearance PBT (the audit claimed the PBT "pins row-count/insulation-class
invariants" that a `+1e-9` bias does not disturb — but
`test_prop_measured_mm_is_actual_copper_gap` recomputes the exact copper gap).

---

## 4. loaders (temper-io-types / design-bundle parse-engine)

Suites-only: the six io `*_pbt.py` files + `test_footprint_library.py` +
`test_reference_aliases.py` + `test_netclass_loader.py` +
`test_config_validation.py` + `test_seed_filter_config.py`. Differentials
disabled: the six io `*_rust_differential.py` files.

Cross-crate note: the loaders span two crates; every suites-only KILL below
was re-verified under per-mutant isolation (both crates rebuilt pristine
before each mutant) to exclude stale-`.so` contamination. One driver-level
false positive (M4) was found and corrected this way.

| Mutant | Suites-only outcome | Catching test / differential-only assertion |
|---|---|---|
| M1 footprint bounds `len == 2` check dropped | **KILLED** | `test_footprint_library.py::TestLoadFootprintLibrary::test_load_invalid_bounds_format` (plain unit test) |
| M2 `yaml.safe_load` → `yaml.load(Loader=BaseLoader)` | **KILLED** | `test_config_validation.py::test_loss_weight_validation_{inf,nan}`, `test_seed_filter_config.py::TestConfigDefaults::test_config_override_respected` (BaseLoader leaves `inf`/`nan` as strings — the validation-error and override tests diverge) |
| M3 self-alias check dropped | **KILLED** | `test_reference_aliases.py::test_manifest_rejects_self_alias` (plain unit test) |
| M4 `str.strip` → Rust `str::trim` | **SURVIVES** | `test_reference_aliases_rust_differential.py::test_escape_decoded_control_char_name_rejected` — the `"\x1c"`-escaped fixture (PyYAML decodes the escape; Python `str.strip` rejects the empty name, Rust trim accepts). The in-crate `rust_trim_keeps_u001c…` unit test documents the primitive but does not exercise `read_aliases`. |
| M5 `_NAME_MAP` `zone_membership` alias dropped | **KILLED** | `test_config_loader_pbt.py::test_p3_loss_weights_name_mapping` |
| M6 `allow_neckdown` default flipped | **KILLED** | `test_config_loader_pbt.py::test_p1_preprocess_parity` (generated configs include `allow_neckdown`) |
| M7 differential-pair key-existence fallback | **KILLED** | `test_config_loader_pbt.py::test_p5_differential_pair_or_semantics` (the `separation_mm: 0` discriminator is the property's own anchor) |
| M8 CPython `round()` → `f64::round` | **KILLED** | `test_reference_loader_pbt.py::test_p1_compute_design_stats_parity` / `::test_p3_component_area_accounting` / `::test_p6_rounding_matches_cpython` (the PBT recomputes `round(x, n)` — its hypothesis corpus includes the exact `0.0625`-class ties) |
| M9 `loops[:3]` cap dropped | **SURVIVES** | `test_reference_loader_rust_differential.py::test_infer_quality_config_loop_cap_matches_oracle` |
| M10 `LossConfig.enabled` default flipped | **SURVIVES** | dict-form-losses discriminator / production-fixture differential |

**Verdict: RETAIN** (3/10 survive: M4, M9, M10). **Audit refuted on 4** — the
audit predicted M1/M2/M6/M8 differential-only; M1/M2/M3 are killed by plain
unit tests, M6/M8 by the config/reference-loader PBTs. The audit's "M9 →
PBT P5" claim is also wrong (M9 survives; the loop-cap pin is
differential-only). The two structurally-differential mutants the audit
identified (M2 PyYAML call-back, M4 `str.strip`) survive M2 only via the
unit-test gap closing it — M4 is the genuinely structural survivor here.

---

## 5. Survivors' discriminating assertions (actionable)

Every survivor's discriminating assertion lives **inside** a
`test_*_rust_differential.py` file:

- **priority** (3): `test_priority_rust_differential.py::test_enum_str_and_repr_identical`,
  `::test_placement_phase_defaults_identical`,
  `::test_routing_phase_defaults_and_round_trip_identical`.
- **constraints** (5): `test_compiler_rust_differential.py::test_escape_none_clearance_default_three_mm`
  (M3); `::test_centroid_neumaier_cancellation` (M4's differential arm —
  killed in-suite by the unit test instead); `test_reporter_rust_differential.py::test_spacing_message_multi_decimal_threshold`
  (M5), `::test_corridor_check_exact_half_width_clear` (M6); builder
  differential `zone=""` case (M8); random-scorer differential (M10).
- **drc contracts** (11): all in `test_drc_contracts_rust_differential.py`
  (see §3b list).
- **drc clearance** (4): `test_clearance_validator_rust_differential.py`
  (`test_same_domain_functional_pairing`, `test_report_sorted_worst_first`,
  `test_verify_identical`/`test_matrix_values_pinned`,
  `test_verify_stats_components_and_rows`).
- **drc validation** (10): the respective
  `test_{drc_oracle,tht_check,geometric,drc,drc_fence}_rust_differential.py`.
- **loaders** (3): `test_reference_aliases_rust_differential.py::test_escape_decoded_control_char_name_rejected`
  (M4); `test_reference_loader_rust_differential.py::test_infer_quality_config_loop_cap_matches_oracle`
  (M9); the dict-form-losses / production-fixture config_loader differential
  (M10).

## 6. What refutes / refines the audit

The audit's **4/4 RETAIN verdict holds**; its *sampling* was wrong about
individual mutants in **12 of 51** cases:

1. **constraints M1/M2/M11** — predicted differential-only (exact-threshold).
   Killed by `test_existing_constraint_integration.py` (exact-boundary
   assertions at 15.0/8.0 mm) and by `test_reporter_pbt.py::test_p3…` (the
   hypothesis floats strategy generates exact-boundary values, so the audit's
   "random corpus almost never lands exactly on a threshold" does not hold
   for this property).
2. **constraints M4/M7** — predicted differential-only; killed by in-crate
   Rust unit tests (`neumaier_matches_cpython_sum`,
   `find_similar_prefix_and_suffix`).
3. **drc validation M4/M5** — predicted differential-only; killed by
   `tests/validation/test_trace_analyzer.py` (delegates to the Rust kernels).
4. **drc clearance M10** — predicted differential-only (`measured_mm` bit
   pins); killed by `test_clearance_validator_pbt.py::test_prop_measured_mm_is_actual_copper_gap`,
   which the audit's sampling missed.
5. **loaders M1/M2/M3/M6/M8** — predicted differential-only; killed by plain
   unit tests (`test_footprint_library.py`, `test_reference_aliases.py`,
   `test_config_validation.py`, `test_seed_filter_config.py`) and the
   config/reference-loader PBTs.
6. **loaders M9** — the audit said PBT P5 catches it; it **survives** (the
   loop-cap pin is differential-only).

Two of the audit's three "PBT genuinely covers" loaders claims (M5/M7) were
right; M9 was wrong.

## 7. Recommendation

**Keep all four differentials.** None is removable under the R20 criterion:
every module still has ≥ 3 mutants that survive the suites-only run, and
their discriminating assertions exist only inside the differential files.
The strongest individual case is **loaders M4** (the `str.strip` call-back
mutant): structurally uncatchable by a property suite — it is a parity claim
against the pinned oracle's Unicode-whitespace runtime behavior, reachable
only through the differential's escape-decoded-C0-control fixture.

The re-run's main corrective value is that several mutants the audit believed
to be differential-only are actually covered by the suites — so the R20
backlog for the *unsampled* modules should apply this run's suites-only
definition (PBT + MR + Rust unit tests + plain unit files) rather than the
audit's narrower sampling. No state-3 (shim + oracle + differential) deletion
is licensed by this run.

## 8. Run integrity

- Every mutant applied exactly once (unique-anchor assertion) and reverted
  verbatim immediately after its run; every suites-only KILL was re-verified
  under per-mutant isolation (both cross-crate extensions rebuilt pristine
  before each loaders mutant).
- Exit-code discipline: pytest exit 1 and Rust unit-test failures count as
  kills; build/collection failures are INFRA and never kills.
- One contamination false positive was caught and corrected: the driver's
  loaders M4 KILL was caused by a stale cross-crate `.so` (the previous
  design-bundle mutant leaking into an io-types mutant's run); the isolated
  re-run shows M4 **SURVIVES**.
- The campaign ended with a pristine rebuild of all four crates and a green
  full-suite run (1000 tests across the six module suites, see provenance);
  `git diff` is empty and `make extensions-check` reports 0 STALE. Caveat:
  `cargo test -p temper-drc-rs` cannot link on this macOS setup (pyo3
  `_PyBool_Type` flat-namespace SIGABRT, unrelated to any mutant) — the drc
  kernel files carry zero `#[test]`, so no suites-only coverage is lost.

---

## Addendum (2026-08-06, PR #860 — §5 superseded, record kept)

Per the docs-never-drift convention this record is kept verbatim; the
**§5 survivor list above is now stale** and is superseded by PR #860
(`perf/r20-suite-hardening`), which moved the discriminating assertions for
**35 of the 36 survivors into the PBT/MR suites** (one test per module, all
demonstrated to kill their mutants — see the PR body). The last remaining
differential-only survivor, **loaders lM4** (the `str.strip` escape-decoded
C0-control call-back, §5 line "loaders (3)" and §7's
"structurally uncatchable" claim), is closed by a suites-only unit test
(`packages/temper-placer/tests/io/test_reference_aliases.py::test_manifest_rejects_escape_decoded_control_char_source`):
it feeds the `"\x1c"`-escaped fixture through the production
`load_reference_alias_manifest` (no oracle import) and asserts the
`ValueError` — under the trim mutant the name stays non-empty and is
accepted, so the assertion fails. The differential's parity form is retained
(unchanged decision under R20) because it still adds breadth — all of
U+001C-U+001F plus any future Python-whitespace-class divergence — but the
"structurally uncatchable" framing no longer holds.
