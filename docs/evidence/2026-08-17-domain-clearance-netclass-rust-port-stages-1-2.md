<!-- provenance: commit=fbc5ce517fec9bbefcbaf632efa6b0ee4062d047 dirty=UNKNOWN -->
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged at task start, at every rebuild, and at task end (read-only
w.r.t. the board; no board writes attempted). -->

# `domain_clearance.py` / `netclass_constraints.py` Rust-port, stages 1-2 — DONE

Specification: `docs/evidence/2026-08-17-placer-constraint-rust-port-spike.md`
(PR #1319, read via `git show 1e21b6111:...` — not on `main` at task start).
Its findings were taken as verified per task instructions and independently
re-confirmed while executing (e.g. `test_requirement_matrix_values_pinned`
does not exist anywhere in the tree — grepped directly, zero hits, matching
the spike's own "UNVERIFIED, flagged rather than assumed" note).

Commits (original, pre-rebase): `0201767f8` (stage 1), `511f91be8` (stage 2).
Rebased onto main `23af9b29c` (PR #1323) after PR #1324 went CONFLICTING;
final commits on `feat/rust-port-domain-clearance-netclass`: `e9c1773a9`
(stage 1, unchanged by the rebase), `4bee6ac3a` (stage 2, adapted to
#1323's classifier fix), `83e10069d` (rebase follow-up: oracle re-pin +
differential fix). See §Rebase below.

## Stage 1 — finish `domain_clearance.py`, single-source the safety matrix

**What ported / single-sourced.** The `IEC60335_REQUIREMENTS` matrix (6
rows) was hand-duplicated in two places: the Python dict in
`requirements/validators/clearance.py` and `temper-drc-rs`'s own
`MATRIX_ROWS` const. Both now read from ONE source:
`packages/temper-design-bundle/src/safety_value.rs`'s new
`requirement_matrix()` — a `SafetyValue`-typed table (`RequirementRow`
struct) reusing this same module's own recovered Table 17 (basic cell,
doubled per cl. 29.2.3 for reinforced rows) and Table 18 (functional row i)
cells for every **creepage** figure — real `RecoveredPrimary`/`Derived`
provenance, not re-derived, not invented. The **clearance** figures (3.0
basic / 6.0 reinforced / 0.5 functional) stay plain `f64`, not
`SafetyValue`, because they were already flagged UNSOURCED in the pre-port
comments (not a Table 16 value) — wrapping them in `SafetyValue::Derived`
or `RecoveredPrimary` would have manufactured a false provenance chain;
`design_value_mm` (an as-built target, never read by the validator) is
likewise plain `f64`. This was a deliberate design choice, not an
oversight — documented in the module comment and this doc.

**LOC.** `packages/temper-design-bundle/src/safety_value.rs`: +155 (the
`RequirementRow` struct, `requirement_matrix()`, 1 new unit test).
`packages/temper-drc-rs/src/req_safe_01.rs`: net −24 (the 30-line
hand-maintained `MATRIX_ROWS` const + its now-corrected-in-passing stale
doc comment replaced by a 16-line `matrix_rows()` flattener calling the
single source). `domain_clearance.py`: +18/−9 (docstring update only — the
function body was unchanged, since it already read `IEC60335_REQUIREMENTS`
indirectly). `requirements/validators/clearance.py`: net −32 → +10 (the
32-line hand-written dict literal replaced by an 11-line generator function
calling the Rust accessor at import time).

**Wiring proof (live, not by naming).** `req_safe_01_verify_iec60335` — the
CI-gate safety validator per `clearance.py:512`'s `verify_iec60335_compliance`
— calls `matrix_rows()`, which calls `temper_design_bundle::safety_value::
requirement_matrix()` directly (verified: `cargo build`, then
`.venv/bin/python -c "import temper_drc_rs as r;
print(r.req_safe_01_requirement_matrix())"` returns the 6 rows unchanged).
Production `IEC60335_REQUIREMENTS` (`validators/clearance.py`) is built at
import time by calling that same accessor — verified directly: importing
the module and printing the dict shows the same enum-tuple keys, same
insertion order, same values as before. Every existing consumer
(`domain_clearance.py::_matrix_rows()`, `real_board.py`, `drc_result.py`,
`router_v6/_clearance_family_py_oracle.py`'s live import) needed zero
changes.

**Discovered while porting, not fixed (flagged per hard rules).**
`req_safe_01.rs`'s `MATRIX_ROWS` doc comment (pre-port) described PD2
figures (4.0mm basic / 8.0mm reinforced, "currently-ENFORCED PD2... per the
owner's sealed-compartment decision") while the actual array held PD3
figures (6.3/12.6mm) — a documentation-only staleness (handoff §11/§12
pattern: a comment survives a value change). Values were never wrong; only
the prose was. Corrected in the same commit since I was already replacing
that block, but flagged here as its own finding: nobody would have caught
this by reading the code's *behavior* (both the old array and the new
`requirement_matrix()` return the same 6.3/12.6 values); only reading the
comment against the data caught it.

## Stage 2 — port `netclass_constraints.py`'s orchestration

Checked for the coordinating sibling agent (the task's coordination note
promised one editing this file's classifier) before starting: `git log
--all` shows zero commits touching `netclass_constraints.py` this session,
and the file's classification logic (`classify_net_type` call site,
`_NET_TYPE_TO_CLASS`, `_SEVERITY_RANK`) was unchanged from the spike's own
description. Proceeded per the task's explicit permission ("port the
corrected version" if landed first; port unchanged otherwise) and its
"do not fight them over the classification logic" instruction — the
classifier's keyword verdict is preserved byte-for-byte by this port,
confirmed by a differential (below) that would fail if it were not.

**What ported.** The O(n²) cross-class pairing loop, severity-rank
component-class resolution, and `class_pairs` override lookup — the ~110
genuinely-unported LOC the spike identified — into
`packages/temper-orchestration/src/netclass.rs` (new file, 270 LOC incl.
tests/comments; two `#[pyfunction]`s:
`netclass_separated_constraints_py` for the batch orchestration,
`netclass_resolve_component_class_py` so the pre-existing direct unit test
of `_resolve_component_net_class` and the batch path call the identical
Rust kernel and cannot silently diverge). Added `temper-io-types` as a new
unconditional, `default-features = false` dependency of
`temper-orchestration` (matches the existing `temper-geometry`/
`temper-data-model` unconditional-dependency pattern in that same
`Cargo.toml`) to reach `classify_net_type` directly rather than duplicating
its keyword logic — zero wasm32 impact verified (temper-io-types' `pyo3`
is optional, its own default is disabled here).

**What stayed Python, deliberately.** The opaque-object marshalling
(`comp.pins`/`pin.net` `getattr` access — `components`/`netlist` are
placer `Component`/`Net` objects, not plain dicts, matching
`domain_clearance.py`'s own "Python marshals, Rust computes" boundary) and
`_resolve_component_net_class`'s public name/signature (kept for
`tests/pcl/test_netclass_constraints.py`'s pre-existing direct unit tests,
which pass unmodified against the new thin wrapper).

**LOC.** `netclass.rs`: +270 (new file). `netclass_constraints.py`: net
−76 → +136 (the 110-line pairing/severity/override loop replaced by ~90
lines of marshalling + FFI call + an expanded docstring explaining the
2026-08-17 port). `lib.rs`/`Cargo.toml`: +16 (module declaration, 2
pyfunction registrations, 1 new dependency).

**Wiring proof (live, not by naming).** `_encoder_core.py:324-328` is the
production call site — `generate_netclass_separated_constraints` runs on
every CP-SAT full-board solve (unlike `domain_clearance.py`, which the
spike found unwired). Verified directly:
`.venv/bin/python -c "import temper_orchestration as to;
print(hasattr(to, 'netclass_separated_constraints_py'),
hasattr(to, 'netclass_resolve_component_class_py'))"` → both `True`;
`test_golden_board_pumpkin_real_board.py` (the real-board CP-SAT
integration test that imports and calls
`generate_netclass_separated_constraints` on the actual production board
data) passes unchanged.

## Oracles created (not re-pinned — zero existed for either file)

1. `packages/temper-placer/tests/requirements/clearance_oracle/
   _iec60335_requirements_py_oracle.py` (86 LOC) — verbatim pre-port
   `IEC60335_REQUIREMENTS` + its two enums. Differential:
   `test_iec60335_requirements_rust_differential.py` (118 LOC, 5 tests):
   row count, row-for-row bit-exact values (`float.hex()`), insertion
   order, production-dict parity, key-type parity.
2. `packages/temper-placer/tests/pcl/_netclass_constraints_py_oracle.py`
   (184 LOC) — verbatim pre-port `netclass_constraints.py`. Differential:
   `test_netclass_constraints_rust_differential.py` (271 LOC, 19 tests: 6
   classification-only, 13 orchestration scenarios covering every branch —
   cross-class pairing, same-class skip, `existing_constraints`
   suppression incl. the `AdjacentConstraint` non-suppression case,
   `touch_refs`, a real `class_pairs` override from the production YAML,
   multi-component pairing — plus 1 Hypothesis property test, 60 random
   examples over component/net-class combinations).

Both registered in `scripts/oracle_hashes.json` (169 total pinned oracles,
was 167 at task start — **only 2 new entries added; zero existing entries
touched or re-pinned**, verified via `git diff scripts/oracle_hashes.json`
showing exactly the 2 additive lines, one per commit).

## Test counts (measured, this session)

| Suite | Result |
|---|---|
| `cargo test` `temper-design-bundle` (`--lib`) | 52/52 |
| `cargo test` `temper-design-bundle` (`--doc`) | 1/1 |
| `cargo test --features python` `temper-drc-rs` (`--lib` + doctests) | 3435/3435 + 1/1 doctest |
| `cargo test` `temper-orchestration` (`--lib`) | 1168/1168 |
| `cargo test` `temper-orchestration` (`--doc`) | 1/1 (compile_fail) |
| `cargo clippy -D warnings` (both crates) | clean (0 new warnings; 5 pre-existing unrelated `net_class_validation.rs` dead-code warnings, not touched by this work, not introduced by it — confirmed via `git log`/`git status` on that file) |
| `pytest packages/temper-placer/tests/requirements/` | 881/881 (+25 pre-existing skips) |
| `pytest test_domain_clearance.py` | 20/20 (+5 pre-existing skips) |
| `pytest test_clearance_validator_rust_differential.py` | 16/16 |
| `pytest test_clearance_family_rust_differential.py` (router_v6) | 72/72 |
| `pytest test_iec60335_requirements_rust_differential.py` (new) | 5/5 |
| `pytest test_netclass_constraints.py` | 8/8 |
| `pytest test_netclass_constraints_rust_differential.py` (new) | 19/19 |
| `pytest test_golden_board_pumpkin_real_board.py` | 1/1 |
| `pytest test_e2e_netclass_ssot.py` | 4/5 (1 pre-existing, unrelated — see below) |
| `scripts/check_oracle_hashes.py` | 169/169 OK |
| `scripts/check_pyo3_duplicate_registration.py` | 0 duplicates, 692 registrations, 10 crates |

**Pre-existing, unrelated failures encountered (not fixed, not mine):**
- `test_e2e_netclass_ssot.py::test_class_pairs_contain_safety_critical_entries`
  — asserts `"IEC 60335-1" in class_pairs[("ACMains","Signal")]["because"]`;
  the actual string is `"UNSOURCED legacy 6.0mm (debunked... citation...)"`.
  This reads `configs/netclass_rules.yaml` directly (not
  `netclass_constraints.py`'s orchestration); `git diff` confirms that YAML
  file was never touched by either of my commits. A stale-citation-text
  assertion, the exact "running check pinned to a wrong number" pattern
  from handoff §11 — but not introduced or touched by this work.
- `test_heatsink_colocation.py::test_rejects_the_committed_board_placement`
  — asserts `{"U5": 3, "U6": 2}` rotations against the live-parsed board;
  actual is `{"U5": 2, "U6": 1}`. Reads `pcb/temper.kicad_pcb` directly via
  `kicad_parser`, imports nothing from any file this work touched. Board
  sha256 confirmed unchanged throughout.

## Safety matrix: now single-sourced?

**Yes, for stage 1's scope.** The 6-row `IEC60335_REQUIREMENTS`/
`MATRIX_ROWS` duplication the spike flagged (§1a) is collapsed: one array
of literal numbers (`safety_value.rs::requirement_matrix()`), two thin
consumers (`req_safe_01.rs::matrix_rows()` for the Rust validator,
`validators/clearance.py::_build_iec60335_requirements()` for every Python
consumer). Zero values changed — proven by the new differential, not
merely asserted.

**Not addressed (correctly out of scope, per the spike's own §1b/§1c):**
the three-classifier duplication (4-keyword `netclass_constraints.py` /
14-KiCad-NetClass router tables / 5-VoltageDomain `domain_clearance.py`)
remains three homes — the spike's own stage 3, explicitly gated on an
owner classification-scheme decision, not attempted here.

## Behavioural differences found

**None between pre-port Python and post-port Rust** — every differential
(the new matrix one, the new netclass one including a 60-example property
test, and the 6 pre-existing suites the ports run under) passed with zero
divergence. The one real finding was the stale PD2-vs-PD3 doc comment in
`req_safe_01.rs` (§Stage 1 above) — a documentation bug, not a behavioral
one; the underlying values were already correct on both sides before this
port touched anything.

## Rebase onto main PR #1323 — classifier fix, not a refactor

PR #1324 (opened from the original 3 commits above) went CONFLICTING when
main PR #1323 (`23af9b29c`) merged, touching the same file:
`netclass_constraints.py`. #1323 is a **safety fix**, not cosmetic: the old
`_resolve_component_net_class` classified via `core.net_classification.
classify_net_type()` — a net-NAME keyword heuristic — which put K1's HV
relay-contact nets (`power_in.ntc-no`, `w1_1`, `w1_2`) in the same
"signal" bucket as J1's SELV RTD nets, so `ca == cb: continue` silently
dropped the ONE separation constraint that mattered — the pair later
proved unroutable. #1323 replaced it with `design_rules.
get_rules_for_net()`, the same `TEMPER_NET_ASSIGNMENTS`-backed classifier
every other `DesignRules` consumer already uses, and completed 10
`class_pairs` rows (`GateDriveHV`/`GateDriveSELV`) the fix newly activated.

**Rebase mechanics.** `git rebase origin/main` conflicted only in
`netclass_constraints.py` (design-bundle/drc-rs/oracle-hashes/docs files
from stage 1 applied cleanly). Resolution: kept #1323's classifier
entirely (`_SAFETY_CATEGORY_RANK`, `design_rules.get_rules_for_net()`
calls, `_pin_class_infos` — a new shared memoization helper, since
`get_rules_for_net` is a live pyclass method needing the GIL and cannot be
ported to a pure Rust kernel without threading a `DesignRules` reference
across the FFI boundary, out of this stage's scope); re-shaped `netclass.rs`
to receive pre-resolved `(net_class, safety_category, clearance)` triples
per pin instead of raw net names, and do the severity-rank reduction over
that data (`safety_category_rank`, mirroring `_SAFETY_CATEGORY_RANK`
exactly) instead of the old `classify_net_type`-based `severity_rank`. The
O(n²) pairing walk, `existing_constraints` suppression, and `class_pairs`
lookup are structurally unchanged from the original stage-2 port. Removed
the now-unused `temper-io-types` dependency from `temper-orchestration`'s
`Cargo.toml` (added only for the old `classify_net_type` call).

**Oracle re-pinned — deliberate, documented, same discipline PR #1307
used for its own corrected divergence.** `_netclass_constraints_py_oracle.py`
was pinned earlier in this session as a verbatim copy of the file *before*
#1323 landed. After rebasing onto #1323, that pin encoded the SUPERSEDED,
unsafe classifier. Continuing to differentially assert against it would
mean one of two wrong outcomes: the Rust port faithfully reproduces a
safety defect Python already fixed, or the comparison is silently
disabled. Neither is acceptable, so the oracle was re-pinned to #1323's
own committed `netclass_constraints.py` (byte-diffed against
`git show 23af9b29c:...` to confirm exact match before committing) — the
correct pre-Rust-port baseline. This re-pin touches only an oracle created
in *this same session* (`18432f31...` → `f06e0e95...`), not one of the
pre-existing ~187 pinned oracles; `scripts/oracle_hashes.json` stays at
169 total entries throughout (confirmed via `git diff`).

**J1↔K1 verified end-to-end, post-rebase, on the real board** (script run
directly against `pcb/temper.kicad_pcb`, not a mock fixture): J1 resolves
to `Signal`, K1 to `HighVoltage`, `generate_netclass_separated_constraints`
emits exactly one `J1↔K1` `SeparatedConstraint` at **6.0mm** — on both the
Rust-ported path and the re-pinned oracle, with an identical total
constraint count (8978) on both sides. Matches #1323's own evidence doc
measurement (0mm absent → 6.0mm) exactly.

**Test counts, post-rebase:**

| Suite | Result |
|---|---|
| `cargo test` `temper-orchestration` (`--lib`) | 1170/1170 (1 known-flaky test in `marshal.rs`, unrelated file, untouched by any commit here — fails only under parallel execution, passes in isolation and on re-run) |
| `cargo clippy -D warnings` `temper-orchestration` | clean |
| `pytest test_netclass_constraints.py` | 8/8 (main's own #1323 assertions, unmodified) |
| `pytest test_netclass_constraints_rust_differential.py` | 22/22 (13 orchestration scenarios incl. the completed `GateDriveHV`/`GateDriveSELV` `class_pairs` rows + a direct J1/K1-style end-to-end check, 7 classification scenarios incl. the defect-shape check, 60-example property test) |
| `pytest packages/temper-placer/tests/requirements/` (stage 1, re-verified) | 881/881 (+25 pre-existing skips) — unaffected by the rebase |
| `pytest test_e2e_netclass_ssot.py` | 4/5 (1 pre-existing failure — `netclass_rules.yaml` citation text, `git diff` confirms untouched by any commit in this branch) |
| `pytest test_physics_gate.py` | 6 failures in this environment, all `IECCreepageGate` tests needing a resolvable `.kicad_pro` sidecar — entirely inside #1323's own `gates.py`/test file, `git diff` confirms zero commits in this branch touch either file |
| `scripts/check_oracle_hashes.py` | 169/169 OK |

**PR update.** Pushed the rebased history (force-with-lease, since rebase
rewrites commit SHAs) to `feat/rust-port-domain-clearance-netclass`;
`gh pr view 1324` confirms `mergeable: MERGEABLE` (was `CONFLICTING`
before the push).

## What "done" means — checklist

- Rust implementation + thin pyo3 binding: yes, both stages, wired and
  proven live by call-site tracing + direct `hasattr`/import checks, not
  by naming. Re-verified live post-rebase via the direct J1/K1 real-board
  script run (§Rebase above).
- Python that is now dead is deleted, not left as a shim: the 32-line
  `IEC60335_REQUIREMENTS` literal and the netclass pairing loop are both
  gone from their Python files, replaced by thin marshalling + FFI calls —
  not commented out, not `# TODO: remove`.
- Differential oracle created for each port: yes, 2 new oracles, 25 tests
  total across both (5 matrix + 22 netclass, +2 net after the rebase's
  J1/K1 addition and classification-shape additions). Zero *pre-existing*
  oracles touched; the netclass oracle (created this session) was
  deliberately re-pinned once, post-rebase, to track main's safety fix —
  documented above, not silent.
- Full test suites pass: yes, exact counts above; every failure present
  (3 distinct pre-existing issues across both the original work and the
  rebase) is independently confirmed unrelated via `git diff` against the
  specific files each touches.
- Stage 2 was not deferred — the coordination risk named in the original
  task (a sibling mid-edit on the same file) did not materialize before
  the rebase (checked via `git log --all`), and the actual conflict that
  DID arrive (main's own #1323, merged after this work started) was
  resolved by rebasing onto the corrected classifier, not fighting it.
