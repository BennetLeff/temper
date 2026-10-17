# Native bridge toolchain, Part 1

Run on `codex/ps-toolchain-sol` at base `ad5182330` on 2026-09-25. This is a
digital source and toolchain check; physical tests and fabrication are NOT RUN.

The four files in `harness-lab/` are byte-identical to
`archive/zapote-coil-intake-2026-09-25`. The plan names three adapters;
`block_source.run_resolved_export()` also executes
`harness-lab/circuit_export.py`, so that archived runtime dependency was
restored unchanged. The same exporter already exists, byte-identical, in this
unit's `tools/` directory. The `temper-design-bundle` patch applied without
content conflicts. Its Python module has 13 `wrap_pyfunction!` registrations
and no duplicate names. `scripts/gen_wasm_test_registry.py --check` reports
3283 tests across 34 modules, up to date.

The unit source was built with `python3 tools/build_source.py source-build-01`
from this directory, using pinned offline Atopile 0.2.69. The sandbox required
access to the existing `~/.cache/uv`; no toolchain source was changed to work
around that restriction. The output is ignored by `.gitignore` and must be
rebuilt in a new checkout. The receipt reports `compiled-and-exported`, return
code 0, no `FAILED` build report, and these source hashes:

| Source | SHA-256 |
| --- | --- |
| `elec/src/parts.ato` | `615977ea2a6327cf079dc8506bb6c7d464321b7873cd3478d3ef13b0cca503e4` |
| `elec/src/power_stage_120v.ato` | `ecfbf62dcdd027110e5e8d15af29f0f6014f5e153d55268a283a2413caa1c5fb` |

The copied source bytes, script SHA-256 and resolved-export SHA-256 all match
the receipt (`162a59c4defe5c5b27f87920ed6ff1f1e3b4428899f9b49007381799b5a73f03`).
Re-running the wrapper against the existing output raises `FileExistsError`
and leaves the receipt unchanged. The audit on fresh outputs reports 91
components, 67 nets, PASS; its mutation suite passes 18/18 tests, including
the crossed-choke-winding case. After replacing the embedded absolute unit
paths in each copy with `UNIT`, fresh and frozen files are byte-identical:

| File | Normalized SHA-256 |
| --- | --- |
| `default.net` | `147027a79f3ddbbd5809972c26dffcad9f70467ee54e5895a677a7036b93e1aa` |
| `default.csv` | `8f83aa127550526191d3025f93efd9f8d28f4b764520cc1d4fc0e0a6d2d5c7a1` |

The Rust commands used an explicit isolated target to avoid poisoning the
shared PyO3 build output:

```sh
CARGO_TARGET_DIR=/tmp/ps-toolchain-cargo cargo test --locked --offline --manifest-path packages/temper-design-bundle/Cargo.toml
CARGO_TARGET_DIR=/tmp/ps-toolchain-cargo cargo test --locked --offline --manifest-path zapote/Cargo.toml --workspace
```

The design-bundle suite passes 75 unit, 2 compile-fail, 2 integration and 2
doc tests. The Zapote workspace passes 299/299 tests. The 26
`scripts/tests/test_gen_repo_state.py` tests pass. Since `harness-lab/` is new
and untracked in this isolated worktree, the repo-map generator was run with
a temporary Git index/object directory containing those new files; its
`--check` reports OK. Once the files are staged in the integration checkout,
plain `python3 scripts/gen_repo_state.py --check` must report the same result.

The Python extension was built in this worktree's isolated `.venv` (CPython
3.14), leaving the main checkout's editable installations untouched:

```sh
python3 -m venv .venv
env -u CONDA_PREFIX VIRTUAL_ENV="$PWD/.venv" CARGO_TARGET_DIR=/tmp/ps-toolchain-cargo \
  maturin develop --release --manifest-path packages/temper-design-bundle/Cargo.toml \
  --features python,pyo3/extension-module --offline
.venv/bin/python -c 'import temper_design_bundle_python as b; print(all(hasattr(b, f) for f in ("candidate_convert_bridge", "candidate_validate_pin_map")))'
```

The import prints `True`; `check_stale_extensions.check_module()` reports
`temper-design-bundle` **fresh** by mtime. The full ten-crate extension gate is
not green in this new venv because the other nine crates are not installed
there; they were deliberately not rebuilt for this unit. It must be run in
the integration environment after its normal extension rebuild.

Running `.venv/bin/python tools/build_native.py /tmp/ps-native-prepart2` reaches
footprint vendoring and fails at the expected missing Part 2 input:

```text
block_source.BlockSourceError: footprint source missing: .../zapote/power-stage-120v/libraries/temper.pretty/Diode_Bridge_GBJ2510.kicad_mod
```

`poses.json` and `outline.json` are read after vendoring, so this failure is
the expected pre-footprint state. The native source and route wrappers have
not generated or altered a board.
