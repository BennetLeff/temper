# Wave-2 PyAny Removal — Independent Verification & Close-out (2026-08-07)

provenance: worktree=`/private/tmp/wt9-pyany2fix`, branch
`feat/wave4-pyany-removal-wave2`, HEAD == `origin/main` @ `fc05617d5`
(assert-base verified 2026-08-07).

## Purpose

Independent re-verification, on current `origin/main`, of the Wave-4 PyAny
removal wave-2 (the 11 REMOVABLE handles of
`docs/evidence/2026-08-06-pyany-surface-audit-2.md` §4 Wave A), plus a sweep
for any additional REMOVABLE handle the audit's full table might have missed.
No source change is needed or made: **all 11 audit REMOVABLEs are already
dispatched on `origin/main`** — 8 tightened in two prior wave-2 PRs, 3
recorded-not-removable with empirical evidence.

## Summary table — the 11 audit REMOVABLEs, current status

| Handle | Audit claim | Status on origin/main | Evidence (re-verified here) |
|---|---|---|---|
| `BoardState.netlist` (gates.rs:573) | REMOVABLE → `Py<Netlist>` | **RECORDED NOT REMOVABLE** | `TestBoardState::test_all_fields_populated` (test_gate_contract.py:236–257) passes `netlist=object()` and asserts identity; PBT P5 `test_mr4_board_state_payload_independence` (test_gates_pbt.py:462) does `BoardState(board=object())`. The audit's A1 "no test pushes a non-contract payload" is factually wrong. Tightening would `TypeError` and break two R1a pins. |
| `BoardState.board` (gates.rs:575) | REMOVABLE → `Py<Board>` | **RECORDED NOT REMOVABLE** | Same two pins, `board=object()` identity. |
| `BoardState.design_rules` (gates.rs:577) | REMOVABLE → `Py<DesignRules>` | **RECORDED NOT REMOVABLE** | Same two pins, `design_rules=object()` identity. |
| `Issue.severity` (drc_contracts.rs) | REMOVABLE → `Py<Severity>` | **TIGHTENED** | Source: `pub severity: Py<Severity>` (:526); ctor `&Bound<'_, Severity>`. Production: `drc_runner.py:225` `severity = _SEVERITY_MAP[...]` (:60 `dict[str, _Severity]`), `drc_oracle.py:576` same. Pin: `test_issue_severity_typed_identity_and_type`. |
| `Issue.location` (drc_contracts.rs:519) | REMOVABLE → `Option<Py<Location>>` | **TIGHTENED** | Source: `pub location: Option<Py<Location>>` (:538); ctor `Option<&Bound<'_, Location>>`. Production: `drc_runner.py:234`/`drc_oracle.py:570` build `_Location(...)` pyclass or pass `None`. Pin: `test_issue_location_typed_none_and_identity`. |
| `Placement.via_placement` (drc_contracts.rs:1318) | REMOVABLE → `Option<Py<ViaPlacement>>` | **TIGHTENED** | Source: `pub via_placement: Option<Py<ViaPlacement>>` (:1352). Production: `_pipeline_verify.py:98` `placement.via_placement = DRCViaPlacement(vias=...)` (pyclass re-export). Pin: `test_placement_via_trace_typed_identity_and_none`. |
| `Placement.trace_placement` (drc_contracts.rs:1320) | REMOVABLE → `Option<Py<TracePlacement>>` | **TIGHTENED** | Source: `pub trace_placement: Option<Py<TracePlacement>>` (:1354). Production: `_pipeline_verify.py:124` `DRCTracePlacement(segments=...)`. Same pin. |
| `HypergraphFactory.netlist` (hypergraph_factory.rs:117) | REMOVABLE → `Py<Netlist>` | **TIGHTENED** | Source: `pub netlist: Py<Netlist>` (:123). Pin: `test_factory_attributes_parity` (`f.netlist is mixed_netlist`). |
| `MonteCarloSimulator.variables` (manufacturing_monte_carlo.rs:601) | REMOVABLE → `Py<ManufacturingVariables>` | **TIGHTENED** | Source: `pub variables: Py<ManufacturingVariables>` (:609). Pin: `test_monte_carlo_simulator_variables_config_typed_identity`. |
| `MonteCarloSimulator.config` (:603) | REMOVABLE → `Py<MonteCarloConfig>` | **TIGHTENED** | Source: `pub config: Py<MonteCarloConfig>` (:611). Same pin (also asserts omitted-config default is a fresh `MonteCarloConfig` pyclass). |
| `ToleranceAnalyzer.table` (manufacturing_tolerances.rs:518) | REMOVABLE → `Py<ToleranceTable>` | **TIGHTENED** | Source: `pub table: Py<ToleranceTable>` (:526). Pin: `test_analyzer_table_identity_semantics` (`analyzer.table is table`). |

**Result: 8 tightened, 3 recorded-not-removable — all 11 closed.**

## Top-5 empirical re-verification (task requirement)

The dispatch called out re-verifying the top-5 handles empirically rather
than trusting the audit. Done, all confirmed:

1. **`Issue.severity`** — source `Py<Severity>` (drc_contracts.rs:526);
   `drc_runner.py:225` resolves through `_SEVERITY_MAP: dict[str, _Severity]`
   (the `Severity` pyclass singletons), `drc_oracle.py:576` the same. The
   anti-vacuity pin passes a `Severity` member and reads it back `is`, and
   asserts `TypeError` for `object()`.
2. **`Issue.location`** — source `Option<Py<Location>>` (:538). Both runners
   build `_Location(x=…, y=…, layer=…)` or pass `None`. Pin: `None` default,
   `is` identity, `TypeError` for non-`Location`.
3. **`BoardState.netlist`/`board`/`design_rules`** — the audit's REMOVABLE
   classification is **contradicted by the pins**: `test_gate_contract.py:236`
   and `test_gates_pbt.py:462` push `object()` payloads and assert exact
   object identity. Tightening would change observable behaviour (TypeError),
   so the three fields stay `Py<PyAny>`. This matches the wave-1 conclusion;
   the audit's A1 evidence was incorrect and is recorded as such.
4. **`Placement.via_placement`/`trace_placement`** — source `Option<Py<…>>`
   (:1352/:1354). `_pipeline_verify.py:98/124` assign the pyclass re-exports
   after default construction; `from_dict` emits `None`. Pin covers `None`
   default, `is` identity, re-assign-to-`None`, and `TypeError` on non-pyclass.
5. **`HypergraphFactory.netlist`** — source `Py<Netlist>` (:123);
   `extraction/hypergraph_factory.py:67` passes the typed `Netlist` through
   the shim signature; differential constructs `Netlist(...)` pyclasses.

## Sweep — any other REMOVABLE in the audit's full table?

A stored-field sweep was re-run on current `origin/main` (struct-body scoped,
Rust comments/string literals stripped, same methodology as the audit). The
file set carrying stored `Py<PyAny>` fields is **identical** to the audit
base `4da76ebb0` — no new file, and **zero new stored `Py<PyAny>` fields**
were added by the migrations merged since the audit (channel_skeleton,
occupancy_grid, clearance_matrix, _write_board, zone/pour emission,
kicad_exporter, layer_assignment, copper_reach, …). The per-struct delta
between the audit base and current main is exactly the 7 tightened handles
plus `ToleranceAnalyzer.table` (verified by direct source read):

```
REMOVED (audit base → current main):
  HypergraphFactory.netlist            (Py<PyAny> → Py<Netlist>)
  MonteCarloSimulator.variables        (Py<PyAny> → Py<ManufacturingVariables>)
  MonteCarloSimulator.config           (Py<PyAny> → Py<MonteCarloConfig>)
  Issue.severity                       (Py<PyAny> → Py<Severity>)
  Issue.location                       (Py<PyAny> → Option<Py<Location>>)
  Placement.via_placement              (Py<PyAny> → Option<Py<ViaPlacement>>)
  Placement.trace_placement            (Py<PyAny> → Option<Py<TracePlacement>>)
  ToleranceAnalyzer.table              (Py<PyAny> → Py<ToleranceTable>) [direct source read]
ADDED: none
```

The audit's remaining stored fields are INTENTIONAL (202) / STILL-NEEDED
(43) in design-bundle, INTENTIONAL (56) / STILL-NEEDED (25) in drc-rs, and
INTENTIONAL (11) / STILL-NEEDED (5) in io-types — none REMOVABLE. The
"tightenable" container fields the audit §2.1 mentions
(`SegmentMetrics.layers_used`, `NetMetrics.segment_details`,
`RoutingMetrics.net_metrics/failed_nets/timeout_nets`) are container fields
(wave-1 rule: containers are not removable) and are not typed-pyclass
handles. `HypergraphBuildResult` (8 fields, hypergraph_factory.rs:79–102)
remains untightened per Wave D / the #826 ledger. **No additional REMOVABLE
handle exists beyond the 11; all 11 are closed.**

## Identity/type pins (anti-vacuity)

Every tightened handle carries an identity/type pin (existing or added by the
prior wave-2 PRs), all verified present and asserting `is`-identity for the
pyclass cases, `None` for the empty cases, and `TypeError` for non-pyclass
payloads:

- `test_issue_severity_typed_identity_and_type`
  (tests/validation/test_drc_contracts_rust_differential.py:452)
- `test_issue_location_typed_none_and_identity` (:466)
- `test_placement_via_trace_typed_identity_and_none` (:478)
- `test_factory_attributes_parity` (`f.netlist is mixed_netlist`,
  tests/core/test_hypergraph_factory_rust_differential.py:322)
- `test_monte_carlo_simulator_variables_config_typed_identity`
  (tests/manufacturing/test_monte_carlo_rust_differential.py:844)
- `test_analyzer_table_identity_semantics`
  (tests/manufacturing/test_tolerances_rust_differential.py:362)

## Dormant-handle decisions (recorded)

`MonteCarloSimulator` and `ToleranceAnalyzer` are shim-wired with no active
production caller (audit §5). The prior wave-2 PR tightened **and** recorded
them (design-bundle VERIFICATION.md "Dormant-handle decision" section): the
tightening is genuine (the wrapped value IS the pyclass on the exercised
path) and strictly stronger; if the `manufacturing/*` shims are ever retired
they become candidates for the #826 unwired-ledger conversation, which is a
separate decision. Re-verified here: the pins exist, the source types are
correct, and `MonteCarloSimulator.rng` correctly stays `Py<PyAny>` (numpy
Generator, STILL-NEEDED).

## Gates run + results (this worktree, 2026-08-07)

| Gate | Result |
|---|---|
| Extension freshness (`make extensions-check`) | PASS — 13/13 fresh (built `make extensions`) |
| drc-rs + design-bundle differential/PBT suites (drc_contracts, hypergraph, monte_carlo, tolerances) | PASS — 181 |
| Consumer suites: `test_gate_contract.py` (TestBoardState), `test_gates_pbt.py`, drc_runner/drc_oracle/drc/drc_fence/preflight/validation consumer suites | PASS — 138 (3 skip) + 71 + 135 |
| Full `tests/validation` + `tests/manufacturing` + `tests/wave4_phase2` | 1940 pass, 5 fail (all environmental/inherited, below) |
| `tests/pcl` | PASS — 1216 |
| `tests/placer/cp_sat` | 710 pass, 2 fail (environmental) |
| ruff | 41 pre-existing errors (router_v6/stubs/deterministic — warn-only in CI; none in touched surface) |
| vulture gate | FAIL — 3 NEW dead-code, all pcl (#721) + router_v6 (#751) fixtures — inherited, other sessions' surfaces |
| type-check gate | FAIL — 16 violations, all pcl/pipeline/regression/router_v6 — the known "main type-check drift" |
| import-linter gate | PASS |
| coverage gate | FAIL (warn-only in CI) — inherited "coverage 177" entries; allowlist unchanged |
| #826 dead-kernel gate (static mode, as CI runs) | PASS — 727 registered, 79 unwired all ledgered |
| `cargo test` temper-design-bundle | PASS — 26 |
| `cargo test` temper-drc-rs | darwin dyld `_PyBool_Type` abort — the documented macOS-only limitation (python-tests.yml:882–897); runs in CI on Linux |
| `cargo clippy` temper-drc-rs (lib + tests, -D warnings) | PASS |
| `cargo clippy` temper-design-bundle | 1 pre-existing error in `kicad_exporter_geometry.rs:202` (#861 surface; `neg_cmp_op_on_partial_ord` fires on local rust 1.92, not in wave-2 files) |
| hasattr smoke (all 14 tightened/kept pyclasses import) | PASS |

**Environmental/inherited test failures observed (not caused by this wave;
zero source changes were made in this session):**

- `test_mfem_runner` — MFEM binary not installed (`/tmp/mfem_tempsolve`).
- `test_netlist_reconciliation` and `TestRealBoardClearanceRepair` (x2) —
  `elec/build/default.net` not built in this worktree (`make netlist`).
- `test_dead_parameter_probe` (x2) — physics-probe floor assertion drift.
- `test_ucc21550_contract_pbt` — ato schematic-content expectation.

## Conclusion

Wave 2 of the PyAny removal is **complete on `origin/main`**: 8 stored
`Py<PyAny>` handles tightened to typed `Py<T>`/`Option<Py<T>>` (each a
behavior-preserving handle swap whose wrapped value IS the same-crate
pyclass on every verified construction path), 3 BoardState handles recorded
non-removable with empirical pin evidence, all anti-vacuity identity pins in
place, VERIFICATION.md R1e records present in both crates, and no further
REMOVABLE handle exists in the audit's full table or in the fields added
since the audit base. The differentials pass unchanged (the tightening IS
the verification). No source change was required or made in this session.
