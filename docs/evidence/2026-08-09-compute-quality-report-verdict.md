# Phase-6 Verdict: `metrics/quality.py::compute_quality_report`

provenance: commit=f3c33206b8c5debfb3ad7600d8956ad7624ba813 dirty=false

Resolves follow-up item 6 of `docs/evidence/2026-08-06-pyany-surface-audit-2.md` (§7
"Phase-6 test-suite territory"). Decision-document only — no source or test file
was modified. Measured against `origin/main` @ `f3c33206` (2026-08-09) in an
isolated worktree (`/tmp/opencode/wt-qverdict`, branch `docs/quality-report-verdict`).

**Verdict: RETIRE — delete the Python `compute_quality_report`, its differential,
and the report-orchestration pin, keeping the Rust `evaluate_quality_py` and the
constituent metric kernels.**

---

## 1. The measured facts

### 1.1 Zero production callers (grep-verified over `packages/temper-placer/src/`)

Every mention of `compute_quality_report` in production source:

| File | Line | Nature |
|---|---|---|
| `metrics/quality.py` | 485 / 521 | the definition + the `DeprecationWarning` |
| `metrics/__init__.py` | 14 / 44 | re-export (`import` + `__all__`) |
| `io/reference_loader.py` | 19 | docstring comment only |

The three production modules that import from `metrics.quality`
(`regression/physics_oracle.py`, `metrics/external_oracle.py`,
`validation/human_reference_extractor.py`) import **only the constituent
kernels** (`thermal_score`, `zone_compliance_score`, `hv_lv_clearance_score`,
`dual_rail_clearance_report`, `loop_area_score`, `compactness_score`,
`connectivity_clustering_score`, `congestion_score`) — never the report.
There is no `from … import compute_quality_report` anywhere under `src/`.

### 1.2 The only exercisers are tests

- `tests/metrics/test_quality_rust_differential.py::TestComputeQualityReport` —
  25 randomized seeds + empty-config + populated-context-raises, bit-identical
  against `_oracle_compute_quality_report` (`float.hex()` keys, type-tagged).
- `tests/metrics/test_quality_rust_differential.py::TestEmptyInputSemantics::test_report_of_an_empty_config_is_six_sevenths_vacuous`.
- `tests/metrics/test_quality_metrics.py::TestComputeQualityReport::test_deprecated_warning`.
- `tests/metrics/_quality_py_oracle.py::_oracle_compute_quality_report` — the
  verbatim pre-migration copy (pinned at `ebf9326ff`), which also carries the two
  report-private helpers `_oracle_total_wirelength` and `_oracle_congestion_score`.
- `tests/validation/_human_reference_extractor_py_oracle.py::_compute_quality_metrics`
  calls `compute_quality_report` (line 403) — but **no test invokes that oracle
  function**: the validation differential only uses `_oracle._compute_routing_metrics`,
  and `_compute_quality_metrics`/`extract_human_reference` are referenced nowhere
  else in the suite. Dormant even inside the test suite.
- `tests/io/_reference_loader_py_oracle.py` mentions it only inside a verbatim docstring.

### 1.3 The constituent kernels' differentials are independent of the report's

`test_quality_rust_differential.py` pins each kernel in its own test class plus
`TestEmptyInputSemantics` (empty/ghost/unresolvable inputs enumerated per kernel),
all against the same `_quality_py_oracle.py`. Deleting `_oracle_compute_quality_report`
(and its two report-private helpers) removes **no** assertion that any surviving
kernel differential depends on. The only things the report differential pins and
nothing else does:

1. the 13-key flat report shape + leaf types,
2. `overall_score` = plain mean of the fixed 7-element order
   `[thermal, zone, clearance, loop, congestion, compact, clustering]`,
   through the PyAny `quality_report_overall_py`,
3. the retired-JAX gate (raises `NotImplementedError` on a populated
   `net_pin_indices`; only reachable with an empty pin table),
4. the documented vacuity: 6 of 7 report subscores are unconditional `1.0` on an
   empty config.

Item 2 is the only one with any arithmetic substance, and it is duplicated in
Rust: `QualityMetrics::from_precomputed` (`types.rs:112`) computes the identical
mean of the identical fixed order, and `placement_metrics::quality_report_overall`
(`placement_metrics.rs:735`, `py_builtin_sum / 7.0`) is unit-tested
(`quality_report_overall_is_the_plain_mean`). Item 1's contract has no consumer
outside the differential itself.

### 1.4 `quality_report_overall_py` is an orphan behind the report

`grep` of the whole repo: its only caller is `metrics/quality.py:558`, inside
`compute_quality_report`. It has no direct test. If the report is retired and this
PyAny is not removed in the same PR, it becomes an unwired orphan — exactly the
class of surface the PyAny audit tracks.

### 1.5 The Rust replacement is real production infrastructure — but not via the report

`evaluate_quality_py` (`lib.rs:442`) is itself test-only (13 tests in
`tests/rust_integration/test_quality_oracle.py`). The **production** quality
pipeline does not use it: `validation/human_reference_extractor._compute_quality_metrics`
uses the two-step `prepare_quality_py` + `evaluate_prepared_py` with the
production marshalers `_netlist_to_oracle_dict` / `_placement_to_oracle_dict`
(same file, lines 382–417). The oracle is wired where it matters; the flat report
never was.

### 1.6 The contracts genuinely differ — WIRE is not a pure delegation

| | `compute_quality_report` (Python) | `evaluate_quality_py` (Rust) |
|---|---|---|
| Input | `PlacementState, Netlist, Board, context, config` objects | 4 PyDicts: `netlist`, `placement`, `spec`, `metrics` |
| Output | flat 13-key dict (`total_wirelength`, 7 scores, 4 dual-rail keys, `overall_score`) | verdict dict `{verdict, metrics{9 keys}, violations}` |
| Dual-rail fields | `clearance_score_3mm/6mm`, `violations_3mm/6mm` | **absent** from `metrics` |
| Wirelength key | `total_wirelength` | `total_wirelength_mm` |
| Score validation | none — passes values through | `NormalizedScore::new` rejects NaN / out-of-`[0,1]` → **`Fail` verdict with zeroed metrics** |
| JAX-retirement gate | raises `NotImplementedError` on populated `net_pin_indices` | no such gate |

On reachable inputs (all scores in `[0,1]`, empty pin table) the 7 subscores and
`overall_score` are bit-identical across both contracts (same kernels, same fixed
summation order, same `/ 7.0`). On degenerate inputs the Rust validation zeroes
the whole report while Python passes the NaN through — a real, currently unpinned
semantic fork that any WIRE would have to resolve deliberately.

---

## 2. The three options, scored

### Option A — WIRE (marshaler + delegate + retire the Python path)

Effort ~1.5–2 days + review; medium risk. Required work:

1. **Marshaler**: `_netlist_to_oracle_dict` / `_placement_to_oracle_dict` already
   exist **in `validation/`**. Importing them into `metrics/quality.py` is a
   layering inversion (validation consumes metrics) and would have to be vetted
   against `.importlinter`; the clean version relocates them into `metrics/`,
   touching production `human_reference_extractor.py` and its docstring.
2. **Reshape, not retire**: `evaluate_quality_py`'s verdict has no dual-rail keys
   and a different wirelength key. The report must still call the Python
   `dual_rail_clearance_report` wrapper (itself a Rust-kernel shim) and rename
   `total_wirelength_mm` → `total_wirelength`. The "Python-only orchestration" is
   *reshaped*, not *retired* — a Python shim survives by construction.
3. **Semantic fork**: the Rust validation zeroes NaN/out-of-range scores; Python
   passed them through. A bit-identical differential **cannot** be written for all
   inputs — only for the reachable `[0,1]` subset the current differential already
   covers. The fork must be decided (accept + pin, or change Rust — a bigger scope).
4. **Synthesized spec**: `compute_quality_report` takes no spec; the marshaler
   must invent one. It does not affect the metrics output, but it is a hidden
   contract choice.

Value returned: a deprecated function with **zero production callers** gets a
round-trip through a verdict shape that does not carry the report's own fields.
The differential would prove, for inputs the current differential already proves,
that the round-trip preserves the report. **The value does not clear the bar the
task sets for WIRE** ("retire the Python-only path", "bit-identical output").

### Option B — KEEP both dormant

Effort ~0; risk 0. But it preserves a permanently-deprecated surface whose
deprecation message points at a test-only function, and leaves §7 item 6
re-deferred with no sharper trigger than today. The re-decide trigger would be: a
production consumer of the flat 13-key report (unlikely — production already uses
the verdict pipeline), or the report shape being needed again. This is defensible
as migration-validation preservation, but it is the status quo the audit flagged,
not a resolution.

### Option C — RETIRE the Python report

Effort ~0.5 day + review; low risk. Deletes the deprecated surface, the
report-orchestration pin, and the orphan `quality_report_overall_py` PyAny in one
PR, while keeping the Rust oracle (`evaluate_quality_py` stays exercised by
`test_quality_oracle.py`) and every constituent kernel + its differential. The
only pin lost is the 13-key report shape (test-internal, no consumer) and the
report's overall-mean exercise (arithmetic duplicated + unit-tested in Rust,
`types.rs:112` / `placement_metrics.rs:735`).

---

## 3. Verdict and justification

**RETIRE** (Option C).

- **Zero production callers is measured, not asserted** (§1.1): no consumer
  exists to migrate, so the deprecation's "no migration cost" window is *now*,
  not later. Both ends are dormant today; that is the cheapest possible removal
  point, and it is exactly the state §7 item 6 says should be resolved.
- **WIRE fails its own acceptance test** (§1.6): the differential cannot be
  bit-identical across all inputs (Rust validation zeroes what Python passed
  through), and the dual-rail/rename reshape keeps a Python shim alive, so the
  "retire the Python-only path" promise is not actually deliverable. It would
  also invert the `validation → metrics` layering or force a relocation, all to
  re-wire a function nobody calls.
- **Nothing of value is lost** (§1.3): the kernels' differentials are fully
  independent; `overall_score`'s mean is duplicated and unit-tested in Rust.
  The report shape is a contract with no consumer.
- **It shrinks the PyAny surface** (§1.4): removing `quality_report_overall_py`
  (and the now-uncalled `placement_metrics::quality_report_overall`) in the same
  PR prevents leaving a second unwired orphan behind the one the audit flagged.
  The audit item's own framing ("honest decision is Phase-6 test-suite
  territory") resolves to the deletion branch, not the keep branch.

**What is NOT retired**: `evaluate_quality_py`, `prepare_quality_py`,
`evaluate_prepared_py`, all seven metric kernels, `dual_rail_clearance_report`,
and the production oracle wiring in `human_reference_extractor.py`.

---

## 4. Concrete next steps for the implementing agent

Do all of the following in **one** PR. No new scripts, so `scripts/manifest.yaml`
is untouched. Run `make regen`/`regen-check` and the standard gates before push.

1. **Production — `packages/temper-placer/src/temper_placer/metrics/quality.py`**:
   delete `compute_quality_report` (lines 485–574) and `total_wirelength`
   (lines 84–113, the deprecated JAX stub whose **only** caller in `src/` is the
   report — deleting it prevents a second orphan). Keep `_clearance_boxes` and the
   seven metric functions unchanged.
2. **Production — `metrics/__init__.py`**: drop `compute_quality_report` and
   `total_wirelength` from the import block and `__all__`. Keep every other export.
3. **Rust — `packages/temper-quality-oracle/src/lib.rs`**: delete the
   `quality_report_overall_py` `#[pyfunction]` (line 773) and its
   `m.add_function(...)` registration (line 915). Optionally delete
   `placement_metrics::quality_report_overall` (line 735) — its only caller was
   the pyfunction; the mean survives in `QualityMetrics::from_precomputed`.
   Rebuild with `make extensions` and refresh extension stamps
   (`scripts/write_extension_stamps.py`), then `uv run --no-sync python
   scripts/check_stale_extensions.py` → 0 STALE.
4. **Tests — `tests/metrics/test_quality_rust_differential.py`**: delete
   `TestComputeQualityReport` (lines 797–864), the vacuity test
   `test_report_of_an_empty_config_is_six_sevenths_vacuous` (lines 970–1005), and
   the now-unused `_oracle_compute_quality_report` import (line 65). All other
   kernel classes stay.
5. **Tests — `tests/metrics/test_quality_metrics.py`**: delete
   `TestComputeQualityReport::test_deprecated_warning` and the
   `compute_quality_report` import (line 11).
6. **Oracle — `tests/metrics/_quality_py_oracle.py`**: delete
   `_oracle_compute_quality_report`, `_oracle_total_wirelength`,
   `_oracle_congestion_score`, and extend the documented "allowed edits" list in
   the module docstring. This **changes the oracle's bytes**: update
   `scripts/oracle_hashes.json` in the same PR via `make regen` (the check is a
   STALE-pin drift, justified by the deletion; see AGENTS.md "oracle drift").
7. **Docs** (documentation-sync rule): update the `compute_quality_report`
   examples/prose in `docs/solutions/architecture-patterns/quality-metrics-built-but-never-connected-2026-07-01.md`
   and `…/wiring-dark-physics-metrics-oracle-2026-07-02.md`, and the deprecated-call
   comment in `io/reference_loader.py:19`. Cross-reference this verdict from
   `docs/evidence/2026-08-06-pyany-surface-audit-2.md` §7 item 6 (mark RESOLVED).
8. **Gates**: `uv run python scripts/import_linter_gate.py`, `make regen-check`
   (oracle-hash + hash-order), the coverage gate (deletions can only shrink the
   allowlist), `make extensions-check`. No `git stash`; push from this branch.

**Re-decide trigger** (if a future caller wants the flat report back): the Rust
oracle would need a report-shaped entry point (dual-rail fields + wirelength
rename) rather than a Python shim — a Rust-side `report_to_py_dict` addition, not
a resurrection of the deleted Python orchestration.
