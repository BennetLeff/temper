# Rust DRC backend: presence gate, before/after, and silent-skip survey

<!-- provenance: commit=db779c81c83de026331f013248e345b465716a41 dirty=UNKNOWN -->

**Date:** 2026-07-26
**Scope:** `packages/temper-drc-rs` (`verify_route_clearance`), its differential
proof (`packages/temper-placer/tests/router_v6/test_clearance_rust_
differential.py`), the CI presence/freshness gate, and a repo-wide survey of
`skipif`/`importorskip` guards that could silently disable a correctness
proof (failure class 6, "Silently skipped," `docs/METHODOLOGY.md` Sec 4).

## TL;DR

- **Falsifier stated before implementing did not fire.** Rebuilding and
  installing `temper-drc-rs` via `maturin develop --release` made
  `verify_route_clearance` importable, and the differential test **genuinely
  passes: 38 passed, 0 skipped, 0 failed** (was 38 skipped, 0 run, before).
- **`verify_clearance()`'s `backend="auto"` now dispatches to Rust by
  default** in this environment (`_HAS_RUST_CLEARANCE = True`).
- **New CI gate** (`scripts/check_rust_drc_presence.py` + a
  `TEMPER_REQUIRE_RUST_DRC=1` job-level env var in `.github/workflows/
  python-tests.yml`, plus a matching fail-closed check inside the
  differential test file itself) makes CI fail hard -- not skip -- when the
  Rust backend is expected but stale or absent. Local dev without the
  wheel built is unaffected (warns, exit 0).
- **Proven in both directions**, with the module genuinely uninstalled and
  genuinely reinstalled (not simulated): absent -> hard failure (script
  exit 1, pytest collection error exit 2); present and fresh -> pass (script
  exit 0, pytest 38 passed).
- **Survey found 40+ files** using `skipif`/`importorskip`. Most guard
  genuinely optional, non-safety-relevant tooling (plotly, websockets). A
  smaller set are real correctness-proof risks, detailed below -- most
  notably four RTD hardware-fault SPICE validation tests gated on `ngspice`
  presence in the CI container (unverified from this checkout), a
  structurally identical "import-only" gap for the two sibling PyO3 crates
  `temper_rust_router` and `temper_constraints`, and six permanently-skipped
  IEC 60335-2-6 safety/EMC/DFM requirement-matrix test files whose validators
  are honestly-labeled `NotImplementedError` stubs.
- **Build-freshness recommendation implemented**: derive the expected
  exported-symbol set from the crate's own `#[pymodule]` registration block
  in `lib.rs` and assert the installed module has every one of them. This is
  the specific, cheap check that would have caught the actual incident (a
  wheel that imports fine but is missing a newly-added symbol).

## 1. Falsifier, stated before implementing

> Rebuilding and installing `temper-drc-rs` via `maturin develop --release`
> into this Python environment will make `verify_route_clearance`
> importable, `_HAS_RUST_CLEARANCE` will become `True`, and
> `pytest test_clearance_rust_differential.py` will report N **passed** (not
> skipped), with 0 failures -- meaning the Rust and Python backends agree on
> every fixture. If any test fails, the port is wrong and must be reported
> as such, not adjusted.

**Result: did not fire.** All 38 tests pass; the port and the Python
reference agree on every fixture, including the stated stress cases
(all-HV falsifier, dense FINE-only). No test was adjusted to make this true.

## 2. Before / after, with run counts (never bare exit codes)

**Before** (module absent from the project's actual test venv,
`/Users/bennet/Desktop/temper/.venv`; this is the interpreter `uv run
pytest` and `python -m pytest` both resolve to for this repo) -- reproduced
directly in this session by uninstalling the wheel and re-running:

```
$ /Users/bennet/Desktop/temper/.venv/bin/python -m pytest \
    packages/temper-placer/tests/router_v6/test_clearance_rust_differential.py -q
collected 38 items
test_clearance_rust_differential.py sssssssssssssssssssssssssssssssssssss [100%]
38 skipped in 0.05s
```

This matches the task briefing's independent measurement (38 skipped in
0.07s) almost exactly -- same file, same count, same silent-pass shape. Two
guarantees are absent here and neither shows up in the exit code (0 either
way): the speedup (Python fallback runs), and the equivalence proof (test
body never executes).

Import surface before the fix, confirmed directly:

```
$ python -c "import temper_drc_rs; print([n for n in dir(temper_drc_rs) if not n.startswith('_')])"
['run_drc', 'temper_drc_rs']
```

**After** (`cd packages/temper-drc-rs && cargo clean && maturin develop
--release`, the crate's own documented workflow per
`docs/solutions/build-errors/stale-rust-build-artifacts-gil-crash-2026-07-06.md`):

```
$ /Users/bennet/Desktop/temper/.venv/bin/python -c "import temper_drc_rs; print(sorted(n for n in dir(temper_drc_rs) if not n.startswith('_')))"
['run_drc', 'temper_drc_rs', 'verify_route_clearance']

$ /Users/bennet/Desktop/temper/.venv/bin/python -m pytest \
    packages/temper-placer/tests/router_v6/test_clearance_rust_differential.py -v
collected 38 items
... 38 individual PASSED lines ...
38 passed in 0.24s
```

`verify_clearance()`'s dispatch (`packages/temper-placer/src/temper_placer/
router_v6/clearance_check.py:107`, `use_rust = backend == "rust" or
(backend == "auto" and _HAS_RUST_CLEARANCE)`) now resolves to Rust under the
default `backend="auto"`, confirmed by `_HAS_RUST_CLEARANCE` being `True`.

Wider regression check (clearance + manufacturing-DRC-integration files,
same as the port's own evidence doc, `docs/evidence/2026-07-26-clearance-
rust-port.md` Sec 5, re-run here with the gate's `TEMPER_REQUIRE_RUST_DRC=1`
set to prove it doesn't break the wider suite):

```
175 passed, 10 xfailed in 2.63s
```

(10 xfailed are the same pre-existing, documented crash-characterization
cases noted in the port's own evidence doc; 0 failed, 0 unexpectedly
skipped.)

## 3. The gate

### Design: what "expected" means, and why

Two independent signals, deliberately layered:

1. **`TEMPER_REQUIRE_RUST_DRC` (env var).** Unset/`0`/`false` = optional
   (local dev default: a contributor without a Rust toolchain, or who
   hasn't run `maturin develop` yet, is not blocked -- the Python fallback
   is a documented, correct, just-slower path). `1`/`true`/`yes` = mandatory.
   Set at the **job level** in `.github/workflows/python-tests.yml`'s `test`
   job, so every step in that job -- the dedicated gate script and the
   pytest run alike -- sees it. This is the "CI vs. local dev" split the
   task asked for: CI is exactly the place where the accelerator and its
   equivalence proof are the thing under test, so a skip there must not be
   silent; a local machine without Rust tooling must not be forced to
   install it just to run the Python-side test suite.
2. **Symbol presence, derived from source** (`scripts/
   check_rust_drc_presence.py`), not a version number. `lib.rs`'s
   `#[pymodule] fn temper_drc_rs(...)` block is parsed for every
   `wrap_pyfunction!(...)` registration, and the installed module is
   checked for each name via `hasattr`. This is what actually reproduces
   the incident: a Cargo.toml version bump is not required for every PR
   (so comparing `Cargo.toml` version against installed package metadata
   would under-detect), but a symbol registered in `#[pymodule]` MUST
   appear on the compiled module by construction (pyo3 guarantees this) --
   so a missing one means the wheel predates the source, full stop, no
   heuristic needed.

### Two layers of enforcement

- **`scripts/check_rust_drc_presence.py`**, wired as a dedicated CI step
  ("Verify temper-drc-rs is fresh (presence + symbol gate)") immediately
  after the existing "Verify temper-drc-rs loads" bare-import step, and
  crucially **before** the later "Run extended test suites in parallel"
  step -- which has `continue-on-error: true` (a separate, pre-existing,
  documented TODO: "parallel test suite flakiness; hard-fail after
  2026-09-01"). This ordering matters: a hard failure *inside* that
  parallel block would currently be swallowed by `continue-on-error` at
  the step level, so the presence gate deliberately lives in its own
  step, without `continue-on-error`, so a stale/missing wheel fails the
  job outright regardless of that pre-existing masking issue.
- **The differential test file itself**
  (`test_clearance_rust_differential.py`) now fails at collection time
  (`pytest.fail(..., pytrace=False)`) if `TEMPER_REQUIRE_RUST_DRC` is set
  and `_HAS_RUST_CLEARANCE` is `False`, instead of relying solely on the
  external script. This is defense-in-depth: even if the dedicated CI step
  above is ever deleted or bypassed, running this test file directly with
  `TEMPER_REQUIRE_RUST_DRC=1` set (as CI now does for the whole job) cannot
  silently skip.

### Fails closed

If `lib.rs` can't be read or its `#[pymodule]` block can't be located,
`check_rust_drc_presence.py` treats that as "cannot determine presence" and
returns exit 1 under `TEMPER_REQUIRE_RUST_DRC=1` -- never a silent pass. It
does not fall back to "assume fine."

### Proof, both directions, using the real module (not a mock)

All four commands below were actually run against the real
`/Users/bennet/Desktop/temper/.venv` install in this session; the module was
genuinely uninstalled and genuinely reinstalled, not simulated, for the
absent/restored pair.

| State | `TEMPER_REQUIRE_RUST_DRC` | `check_rust_drc_presence.py` | `pytest test_clearance_rust_differential.py` |
|---|---|---|---|
| Fresh (real `pip uninstall` + `maturin develop --release`) | `1` | `OK: ... symbols ['run_drc', 'verify_route_clearance'] all found.` exit **0** | `38 passed` exit **0** |
| Fresh | unset | same OK message, exit **0** | `38 passed` exit **0** |
| Stale (shadowed via `PYTHONPATH` with a module exposing only `run_drc`, reproducing the exact original bug) | `1` | `FAIL: ... missing symbol(s) ['verify_route_clearance'] ... STALE ...` exit **1** | n/a (script only; shadow doesn't affect the real venv install used by pytest) |
| Stale (same shadow) | unset | same message, prefixed `WARN`, exit **0** | n/a |
| Absent (`pip uninstall -y temper-drc-rs`, genuinely, twice, verified via `import` failing with `ModuleNotFoundError`) | `1` | `FAIL: temper_drc_rs is not importable ...` exit **1** | `1 error during collection` (pytest.fail at import time), exit **2** |
| Absent (same uninstall) | unset | same message, `WARN`, exit **0** | `38 skipped` exit **0** (documented, expected local-dev behavior) |
| Restored (`maturin develop --release` again) | `1` | OK, exit **0** | `38 passed` exit **0** |

The "absent" row is the literal repro of the original incident's shape (a
stale/missing backend, exit 0 by default) plus proof that setting the CI
signal turns that same condition into a hard, unambiguous failure -- the
gate closes the exact hole this task opened with.

## 4. Survey: other `skipif`/`importorskip` guards

40 files use `pytest.mark.skipif` or `pytest.importorskip`. Grouped by what
each leaves unproven when it fires, most safety-relevant first.

### High: same structural class as the fixed bug (locally-built PyO3 extension, import-only CI check)

- **`packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py`**
  -- `skipif(not _HAS_RUST, reason="temper-rust-router not installed")`.
  `temper_rust_router` is built the same way as `temper_drc_rs` (excluded
  from `uv sync` via `--no-install-package`, built separately with
  `maturin develop --release`), and CI's "Verify temper_rust_router loads"
  step (`.github/workflows/python-tests.yml:145-148`) is a bare import
  check with the same blind spot this task just fixed for `temper_drc_rs`:
  it cannot detect a stale wheel missing a symbol. **Not fixed in this
  change** (out of the stated scope, which is `verify_route_clearance`
  specifically) -- **recommended follow-up**: point
  `scripts/check_rust_drc_presence.py` at this crate too (it already
  parametrizes cleanly on `MODULE_NAME`/`LIB_RS`; the one complication is
  that `temper_rust_router`'s `#[pymodule]` also registers classes via
  `m.add_class::<...>()`, which the current symbol extractor does not
  parse -- would need a small extension, not a rewrite).
  What's unproven if this fires silently: Stage-3 SAT topology
  constraint-audit correctness against the Rust solver.
- **`temper_constraints`** (`packages/temper-placer/temper-constraints`) has
  the identical pattern: excluded from `uv sync`, built via `maturin
  develop --release`, and its "Verify temper-constraints loads" CI step
  is also a bare import. No dedicated differential test file was found
  referencing it by a `skipif`/`importorskip` guard in this survey scope,
  but the same import-only blind spot applies to whatever consumes it.

### High: safety-relevant simulation, environment-gated, unverified in the CI container from this checkout

- **`elec/validation/test_rtd_fault_latch_transient_spice.py`,
  `test_rtd_hw_fault_spice.py`, `test_rtd_window_ported_models_spice.py`,
  `test_rtd_window_selected_values_spice.py`** -- all four gated on
  `shutil.which("ngspice") is None`. These are RTD (resistance-temperature
  detector) hardware-fault and fault-latch SPICE validations -- safety
  simulation, not incidental. `ngspice` is present on this machine
  (`/opt/homebrew/bin/ngspice`) but **no workflow file in
  `.github/workflows/` installs or references `ngspice`**; whether the
  `ghcr.io/bennetleff/temper-ci:latest` container image includes it is
  **UNVERIFIED from this checkout** (the Dockerfile for that image is not
  in this repo). If it does not, these four tests silently skip in every
  CI run, and RTD fault-detection SPICE validation is unproven on every
  merge with no visible signal. Recommend either confirming `ngspice` is in
  the CI image, or adding the same `TEMPER_REQUIRE_*`-style hard-fail
  pattern used here, gated on `RUN_HARDWARE_SIM=1` or similar for whichever
  CI job is supposed to guarantee it runs.
- **`packages/temper-placer/tests/validation/test_mfem_runner.py`** --
  `skipif(..., reason="MFEM binary not compiled")` (two occurrences).
  Finite-element EM simulation validator; if the MFEM binary isn't built in
  CI, these silently skip and EM-field correctness against the FEM oracle
  is unproven. Also **UNVERIFIED from this checkout** whether CI compiles
  MFEM.

### Medium: independent-oracle checks (methodology's "Contradiction" axis), tool-presence gated

- **`packages/temper-placer/tests/io/test_dsn_kicad.py`** --
  `skipif(not shutil.which("kicad-cli"), ...)`.
- **`packages/temper-placer/tests/cli/test_validate_command.py`** --
  `KICAD_CLI_AVAILABLE` gate.
- **`packages/temper-placer/tests/validation/test_drc_runner.py`** --
  `TestDrcRunnerIntegration` gated on `sys.platform != "linux" or not
  is_kicad_cli_available()`, with the explicit comment "real KiCad DRC is
  verified by the Linux truth-gate runner." A double-condition guard
  (platform AND tool) is more fragile than a single one: if the CI
  container ever drops `kicad-cli`, this reads as "not on Linux" levels of
  plausible and stays silent. `kicad-cli` is confirmed present on this dev
  machine and is invoked elsewhere in CI (schematic regeneration), so this
  is lower-probability than the ngspice/MFEM cases but the same shape.
  What's unproven if it fires: `kicad-cli` used as the independent oracle
  against this project's own DRC runner never actually cross-checks.

### Medium: honestly-labeled, permanent TDD stubs -- not a regression, but a real, standing gap

- **`packages/temper-placer/tests/requirements/safety/test_clearance.py`**
  (REQ-SAFE-01, IEC 60335-2-6 creepage/clearance),
  **`.../requirements/emc/test_bypass_caps.py`**,
  **`.../requirements/emc/test_emi_filter.py`**,
  **`.../requirements/emc/test_ground_plane.py`**,
  **`.../requirements/dfm/test_placement_rules.py`**,
  **`.../requirements/dfm/test_test_points.py`** -- all six gated on a
  `VALIDATORS_AVAILABLE` flag that is only `True` if
  `tests/requirements/validators/clearance.py` (and siblings) actually
  implement their check functions; confirmed by reading
  `validators/clearance.py` that `check_domain_clearance`,
  `check_creepage_path`, and `verify_iec60335_compliance` all currently
  `raise NotImplementedError(...)`. Unlike the other findings here, the
  skip reason is honest ("not yet implemented") and this is not a
  regression -- it is a known, visible TDD placeholder. It is nonetheless
  worth surfacing prominently: **formal IEC 60335-2-6 safety-clearance
  compliance, EMC (bypass caps / EMI filter / ground plane), and DFM
  (placement rules / test points) requirement matrices have zero executed
  test coverage today**, continuously, and nothing in the CI summary
  distinguishes "6 requirement files, 0 of them proving anything" from "6
  requirement files, all green."
- **`packages/temper-placer/tests/validation/test_mfem_gate.py`** --
  `skipif(..., reason="real MFEM gate integration deferred")`, same honest-
  stub shape as above, smaller in scope (one file).

### Low: optional pure-Python/pip dependencies, structurally different risk profile

`jax` (`test_cli_error_handling.py`, `test_multi_seed.py`,
`test_validate_command.py`, `test_export_command.py`,
`test_dpp_multiseed_ab.py`, `test_roundtrip.py`), `numba`
(`test_los_numba_correctness.py`, `test_wave4_numba_astar.py` -- itself a
Numba-vs-Python differential test, structurally identical in *shape* to the
fixed bug, but **not** the same risk level because `numba` is a normal `uv`-
managed dependency, not a locally-built extension), `shapely`
(`test_drc_inflate.py`, `test_routability_check.py`), `plotly`
(`test_board_renderer.py`, `test_loss_plots.py`, `test_status.py`),
`websockets` (`test_server.py`). All of these are installed automatically
and version-pinned by `uv sync`/`uv.lock` -- there is no manual build step
that can leave them stale, which is the structural precondition that made
the `temper_drc_rs` bug possible in the first place. Flagged for
completeness, not recommended for immediate gating.

### Negligible: checked-in fixtures/config, effectively unconditional in a normal checkout

`_TEMPER_CONFIG.exists()` (`test_isolation_slots_extraction.py`,
`test_isolation_slots_in_slot_generation.py` -- config file confirmed
present at `configs/temper_deterministic_config.yaml`), `MINIMAL_PCB.exists()`
(`test_roundtrip.py`, 13 occurrences, fixture confirmed checked in),
`TEMPER_CONFIG_PATH`/`TEMPER_PCB_PATH` (`test_phased_placement_pipeline.py`,
`test_phased_stage_integration.py`), `_FIXTURE_PCB.exists()`
("quarantined fixture," `test_input_stage_identity_preflight.py`),
`is_pcb_available("bitaxe_ultra")` (`tests/fixtures/external/__init__.py`,
deliberately external/opt-in fixture), Windows-only (`os.name == "nt"`),
Plotly-inverse tests deliberately checking the "missing" branch
(`test_board_renderer.py:417`, `test_status.py:490,497`,
`test_server.py:455`). These fire only if the repo checkout itself is
broken or a file is deliberately not fetched, not from an environment gap.

## 5. Build-freshness recommendation (implemented)

**Recommendation:** compare the *exported symbol set* of the installed
extension against what the crate's own `#[pymodule]` registration block in
`lib.rs` currently declares. Not a `Cargo.toml` version bump (not required
on every change, so it under-detects), not a build hash (would need to be
computed and stored somewhere at build time, adding a second moving part).
Symbol presence is derivable for free from source that already exists and
is guaranteed consistent with the compiled artifact by pyo3's own
`#[pymodule]`/`wrap_pyfunction!` machinery -- if a name is registered, it
WILL be an attribute on the imported module, or the wheel is stale by
definition.

**Implemented**: `scripts/check_rust_drc_presence.py`, described in Sec 3
above, wired into `.github/workflows/python-tests.yml` as a non-continue-
on-error step and into the differential test file as a second layer.
**Not implemented for the sibling crates** (`temper_rust_router`,
`temper_constraints`) in this change -- flagged as a recommended follow-up
in Sec 4, since their `#[pymodule]` blocks also register classes
(`m.add_class::<...>()`), which the current regex-based symbol extractor
does not yet parse (only `wrap_pyfunction!` function registrations).
Extending it is a small, well-scoped addition, not a rewrite, but doing it
without also verifying against those crates' actual differential tests
would be adding an untested check -- left for a follow-up that can verify
it the same way this one was (real uninstall/reinstall, not simulated).

## 6. UNVERIFIED

- Whether the `ghcr.io/bennetleff/temper-ci:latest` container image
  installs `ngspice` (affects 4 RTD SPICE validation tests, Sec 4) or
  compiles the MFEM binary (affects `test_mfem_runner.py`, Sec 4) -- the
  Dockerfile for that image is not present in this repository checkout.
- Whether `temper_rust_router` or `temper_constraints` currently have a
  live stale-wheel exposure identical to the one fixed here for
  `temper_drc_rs` -- their CI steps have the same structural shape (bare
  import only) but this was not independently reproduced the way the
  `temper_drc_rs` incident was (Sec 3's both-directions proof used the
  real module).
- Whether `kicad-cli`'s absence would actually go unnoticed in the real CI
  container (it is invoked by other steps in the same workflow for
  schematic regeneration, which is indirect evidence it's present, not
  direct proof for the specific test-gating call sites in Sec 4).

## Files touched

- `scripts/check_rust_drc_presence.py` (new) -- the presence/freshness gate
  script.
- `.github/workflows/python-tests.yml` -- job-level `TEMPER_REQUIRE_RUST_DRC:
  "1"` env var on the `test` job; new "Verify temper-drc-rs is fresh
  (presence + symbol gate)" step after the existing bare-import check.
- `packages/temper-placer/tests/router_v6/test_clearance_rust_differential.py`
  -- fail-closed check at collection time when
  `TEMPER_REQUIRE_RUST_DRC=1` and the Rust backend is unavailable, plus
  updated module docstring.
- `scripts/manifest.yaml` -- manifest entry for the new script (required by
  the pre-existing `check_manifest_gate.py` CI gate).
- This file.
