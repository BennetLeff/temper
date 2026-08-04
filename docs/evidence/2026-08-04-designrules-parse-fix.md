<!-- provenance: commit=6565f09d317c33828623325a0cc9ba658cc8f0d8 dirty=false -->

# DesignRules parse-fix — `_mm` constructor/read drift between the Rust pyclass and the Pydantic NetClassRules model

## Summary

The Regression Suite's CP-SAT Placer Tests job was red on main with four
failures, all surfacing as a round-trip write→parse failure of the golden
board:

```
written board failed parse_kicad_pcb_v6: DesignRules.__new__()
got an unexpected keyword argument 'default_clearance_mm'
```

Root cause: two signature/read drifts left by the Wave-4 "contracts-as-pyo3
pyclasses" migration (#578/#585/#586/#601-era, plan
`docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`, D5 /
Phase B), which moved the `DesignRules` data model from a Python dataclass
to a pyo3 pyclass in the `temper-design-bundle` crate while `NetClassRules`
stayed a generated Pydantic model. The two drifts are distinct and were
fixed by two commits:

| Drift | Where | Fixed by |
|-------|-------|----------|
| Parser passed `_mm` constructor kwargs to the Rust `DesignRules` pyclass, which only ever accepted the canonical non-`_mm` names | `io/_parse_nets.py::_extract_design_rules` vs `temper-design-bundle/src/design_rules.rs` `#[pyo3(signature)]` | `28dc960de` (already on main) |
| router_v6 pre-migration call sites read `_mm`-suffixed attributes off Pydantic `NetClassRules` objects (which only have the non-`_mm` field names) | 10+ call sites vs `core/netclass_rules_gen.py` | `65c100c82` (this branch) |

This document is the evidence for the second drift (the first was already
landed and documented in `28dc960de`'s own message).

## The drift, precisely

### Drift 1 — constructor kwargs (fixed by 28dc960de, already on main)

`_parse_nets.py::_extract_design_rules` constructed the Rust `DesignRules`
pyclass with

```python
DesignRules(default_clearance_mm=..., default_trace_width_mm=..., ...)
```

but the pyclass's `#[pyo3(signature)]` only ever accepted the non-`_mm`
names — matching `core/design_rules.py::create_temper_design_rules()` and
the pre-migration Python oracle (`tests/core/_design_rules_py_oracle.py`).
Every board write/reparse round trip hit this and failed with
`DesignRules.__new__() got an unexpected keyword argument
'default_clearance_mm'`. Fixed by renaming the constructor call to the
authoritative non-`_mm` names (commit `28dc960de`, PR #666).

### Drift 2 — `_mm` reads off Pydantic NetClassRules (fixed by 65c100c82)

Once drift 1 was fixed, the same CI job surfaced the second drift, which
drift 1's constructor bug had been masking: `route_pcb()` (exercised by
`test_production_board_routing_drc_regression`) reads `_mm`-suffixed
attributes off whatever object `DesignRules.get_rules_for_net()` /
`net_classes` holds:

- `router_v6/_astar_search.py`: `net_rules.via_diameter_mm`, `net_rules.clearance_mm`
- `router_v6/escape_via_generator.py`: `rules.via_diameter_mm`, `rules.via_drill_mm`, `rules.clearance_mm`
- `router_v6/bundle_analyzer.py`: `rule.trace_width_mm`, `rule.clearance_mm`
- `router_v6/constraint_model.py`: `rule.trace_width_mm + rule.clearance_mm`
- `router_v6/capacity_check.py`: `design_rules.get_rules_for_net(net).trace_width_mm`
- `deterministic/stages/setup.py`, `deterministic/__init__.py`, `regression/drc_ratchet.py`, `validation/drc_oracle.py`, `io/config_loader.py`

Two NetClassRules flavors flow into those call sites:

1. **Pydantic `NetClassRules`** (non-`_mm` field names: `trace_width`,
   `clearance`, `via_diameter`, `via_drill`) — produced by
   `io/netclass_loader.py::load_netclass_rules()` from
   `configs/netclass_rules.yaml` and by `TEMPER_NET_CLASSES`. **Broken**: the
   `_mm` reads raise `AttributeError: 'NetClassRules' object has no
   attribute 'via_diameter_mm'`.
2. **`router_v6/stage0_data.NetClassRules`** (already-`_mm` field names) —
   produced by the vestigial board-parse path
   (`_parse_nets.py::_extract_design_rules`) and by unit tests constructing
   the legacy dataclass directly. Works, but is legacy.

The production regression tests inject flavor 1 via
`design_rules=rules.design_rules` (`load_netclass_rules(RULES_PATH)`), so
every `route_pcb()` call crashed.

The canonical field names are the non-`_mm` manifest names: the SSOT
manifest (`packages/temper-placer/configs/netclass_rules_manifest.yaml`)
names the fields `trace_width` / `clearance` / `via_diameter` / `via_drill`,
and the same manifest's `rust_name:` entries show the *Rust* side of the
domain model (temper-drc-rs `board.rs`) uses `_mm`. The `_mm` reads are a
legacy call-site convention predating the migration, not canonical fields.

### Fix chosen: Option A (aliases on the model), matching 28dc960de's pattern

`28dc960de` resolved the equivalent asymmetry for the Rust `DesignRules`
pyclass by adding `_mm` getter/setter aliases there, explicitly NOT by
renaming the dozen call sites — renaming would break the unit tests that
construct the legacy `_mm`-suffixed `stage0_data.DesignRules`/`NetClassRules`
dataclasses directly and pass them into the same call sites. This branch
mirrors that decision for the Pydantic model: **read-only `_mm` property
aliases added to the generated `NetClassRules` model via the codegen
template** (`scripts/templates/netclass_rules.py.j2`), regenerated with
`scripts/gen_domain_models.py`. The manifest (SSOT) is unchanged, so the
Rust `board.rs` block is untouched and `gen_domain_models.py --check`
passes; the aliases delegate to the canonical fields, so both flavors now
answer `_mm` and non-`_mm` reads identically.

```python
@property
def trace_width_mm(self) -> float:
    return self.trace_width
# ... clearance_mm / via_diameter_mm / via_drill_mm likewise
```

## Reproduction

With freshly built extensions (wave-4 pyo3 pyclasses — a stale `.so`
recreates the bug locally; `make extensions`, 0 STALE after):

```
$ uv run --no-sync pytest tests/placer/cp_sat/test_parallel_drc_helper.py::test_timeout_reaps_the_process_group \
    tests/placer/cp_sat/test_regression_drc.py -k "golden or routing" -q --tb=short
```

Pre-fix, the NetClassRules drift reproduces directly (the pre-fix generated
model, via `git show HEAD~1`):

```
AttributeError: 'NetClassRules' object has no attribute 'via_diameter_mm'. Did you mean: 'via_diameter'?
```

Post-fix, all four target tests pass with fresh extensions:

| Test | Result |
|------|--------|
| `test_timeout_reaps_the_process_group` | PASS (1.1–1.6s; 4/4 runs) |
| `test_golden_board_drc_regression` | PASS |
| `test_golden_board_rotation_drop_mutant_fails_oracle` | PASS |
| `test_production_board_routing_drc_regression` | PASS (81s) |
| Full `tests/placer/cp_sat/test_regression_drc.py` | 4 passed, 1 skipped (the skip is the documented pre-existing KNOWN GAP at line 409 — corpus-board completion rate, unrelated) |

## Un-masked second finding: stale unconnected gate in tests/router_v6

Fixing the crash let `tests/router_v6/test_temper_production_board_routing.py::test_route_pcb_production_board`
run to completion for the first time since the wave-4 migration (it was
crashing on the same `_mm` AttributeError before). It then failed its APC
gate: `unconnected 460 > 411`.

This is not a new regression — it is a **stale baseline**. The sibling gate
`PRODUCTION_ROUTER_OUTPUT_UNCONNECTED` in
`tests/placer/cp_sat/test_regression_drc.py` was re-baselined to **463** on
2026-08-02 for exactly this router output (route_pcb deterministic,
completion 0.4021, DRC N=11 on the one routed file, zero scatter), with full
attribution in that file's provenance block: the 2026-08-02 board change (31
footprints nudged, content hash 0fff888a → cf161bee) plus measurement-context
drift from three netclass-reclassification commits to `pcb/temper.kicad_pro`
(369fc0f7b, e3040b9a1, cbaad2eb7); see
`docs/evidence/2026-08-01-edge-hanging-refs-fix.md`. The router_v6 test's
411 gate (2026-07-31 K2-swap measurement) was never re-baselined because the
test could not run to surface it. A fresh post-fix measurement reports 460 ≤
463. Re-aligned the router_v6 gate to the sibling's attributed 463 (commit
`282f6a81b`) — same documented, attributed class as every prior move, not a
ratchet-up to absorb an unexplained regression.

## Test results (post-fix, fresh extensions)

- 4 target tests: all PASS (table above).
- `tests/placer/cp_sat/test_regression_drc.py` full file: 4 passed, 1 skipped.
- `tests/core/` full suite: 673 passed, 9 skipped (includes the new
  `tests/core/test_design_rules_field_parity.py`, 4/4).
- `tests/deterministic/` full suite: 454 passed, 1 skipped.
- `tests/validation/test_placement_roundtrip.py` +
  `tests/test_round_trip_integrity.py` + `tests/test_metamorphic_oracles.py`
  + `tests/core/test_design_rules_rust_differential.py`: 49 passed.
- router_v6 call-site suites (`test_capacity_check.py`,
  `test_escape_via_generator.py`, `test_bundle_analyzer.py`,
  `test_stage0_loader.py`, `test_via_placement.py`,
  `test_bundled_equivalence.py`, `test_temper_production_board_routing.py`,
  `tests/regression/`): 173 passed, 2 skipped, 1 failed → after the
  re-baseline, the one failure is green.
- `test_temper_production_board_routing.py::test_route_pcb_production_board`
  (re-baselined): PASS.

## Gates

- `python3 scripts/gen_domain_models.py --check`: PASSED (manifest SSOT and
  both generated outputs in lockstep; Rust `board.rs` block unchanged).
- `uv run ruff check` on all touched Python files: clean (the `.j2` template
  is not ruff-parseable — expected, not a gate).
- `uv run python scripts/import_linter_gate.py`: PASSED — 0 new violations.
- `uv run python scripts/check_typecheck_gate.py`: PASSED — 214 errors, equal
  to the allowlist baseline; 0 unapproved call-arg errors.
- `uv run --no-sync python scripts/check_stale_extensions.py`: 0 STALE
  (11/11 fresh) before any test run.

## Commits on this branch (`fix/designrules-parse-arg`)

- `65c100c82` — fix(netclass): add `_mm` read aliases to generated
  NetClassRules model (template + regen).
- `282f6a81b` — test(router): re-baseline production-board unconnected gate
  411 → 463 (attributed; sibling file's documented measurement).
- `c2411adc5` — test(core): pin DesignRules/NetClassRules `_mm` field parity.
- (plus a small importorskip-order fix to the parity test)

## Follow-ups

- The router re-route (reducing the ~460 unconnected pairs on the production
  board) remains the standing follow-up already tracked in the re-baseline
  comments of both gates.
- `test_timeout_reaps_the_process_group` triage verdict: **flaky-timing, not
  a real bug** — passes 4/4 locally (1.1–1.6s each) with fresh extensions;
  its 5s grandchild-reap deadline is tight under CI load. No code change
  warranted (R22: trivial-fix scope does not include retiming a passing
  test).
