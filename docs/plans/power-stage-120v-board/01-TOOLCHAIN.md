# Part 1: bring the native-bridge toolchain onto this branch

**Goal:** make it possible to (a) freeze an Atopile source build of the power
stage and (b) project it into KiCad with the repo's strict source-to-native
bridge. No footprint, placement or board work happens in this part.

**Why this part exists:** the bridge the other zapote boards used lives partly
in files that were never landed on `main`:
- `harness-lab/block_source.py`, `block_native.py`, `buck_native.py`
- ~1,100 lines of Rust in `packages/temper-design-bundle` (functions
  `candidate_convert_bridge`, `candidate_validate_pin_map`, …)

The unit tools that call them already exist here, for example
`zapote/current-sense/tools/build_current_sense_native.py` and
`zapote/rtd/apply_routes.py`.

## Inputs

- Base branch: the tip of `feat/cooker-120v-workspace` (or `main`, once PRs
  #1612 and #1613 have merged).
- Salvage source (read-only): tag `archive/zapote-coil-intake-2026-09-25`.
  Below, `T=archive/zapote-coil-intake-2026-09-25`.

## Steps

### 1.1 Worktree

```sh
cd /Users/bennet/Desktop/temper
git fetch origin
git worktree add worktrees/ps-toolchain -b feat/ps-native-toolchain origin/feat/cooker-120v-workspace
cd worktrees/ps-toolchain
T=archive/zapote-coil-intake-2026-09-25
```

### 1.2 Restore the three harness-lab modules, unchanged

```sh
mkdir -p harness-lab
for m in block_source block_native buck_native; do
  git show "${T}:harness-lab/$m.py" > "harness-lab/$m.py"
done
```

Then:

1. Open each file and list every `import`. Any import of another
   `harness-lab` module that you didn't restore must be restored the same way.
   Known: `block_native` imports `buck_native` and `pcbnew`; `block_source`
   imports `gen_pcb_skeleton` and `gen_schematics` from `scripts/`, which is
   already on the branch.
2. **Do not edit these files** beyond what an import error forces. If you must
   edit, record the reason in the commit message.
3. Write `harness-lab/README.md` (5–10 lines). It should say:
   - these three modules are the retained native-bridge adapters
   - the rest of `harness-lab/` stays at tag `${T}`
4. Add `harness-lab` to `DIRECTORY_PURPOSE` in `scripts/gen_repo_state.py`, for
   example: `"harness-lab": "Retained KiCad native-bridge adapters used by zapote unit tools"`.
   Then run `python3 scripts/gen_repo_state.py` (it rewrites README.md) and
   `python3 scripts/gen_repo_state.py --check`, which must print OK.

### 1.3 Port the Rust bridge functions into `temper-design-bundle`

```sh
git diff origin/main "${T}" -- packages/temper-design-bundle > /tmp/bundle.patch
git apply --3way /tmp/bundle.patch
git status --short packages/temper-design-bundle
```

The expected files are `src/atopile.rs` (new, about 478 lines),
`src/identity.rs`, `src/lib.rs`, `src/validation.rs` and `src/wasm_test_registry.rs`.

- **If `git apply --3way` leaves conflict markers:** resolve them only if the
  conflict is purely additive, meaning both sides add different functions or
  registrations. For anything else, **stop and ask**.
- **Watch the pyo3 registrations in `lib.rs`.** A later `add_function` of the
  same name silently shadows an earlier one (see the root `AGENTS.md`). After
  applying, run `grep -n "wrap_pyfunction" packages/temper-design-bundle/src/lib.rs`
  and confirm no name appears twice.

Build and check:

```sh
make extensions            # rebuilds pyo3 extensions (several minutes)
make extensions-check      # must report the design-bundle as fresh
uv run --no-sync python -c "import temper_design_bundle as b; print(all(hasattr(b, f) for f in ['candidate_convert_bridge','candidate_validate_pin_map']))"
# must print True
cargo test --locked -p temper-design-bundle   # must pass
```

If `wasm_test_registry.rs` changed, look for the repo's registry generator and
check (`scripts/gen_wasm_test_registry.py`) and run its `--check` mode. It must
pass.

### 1.4 Unit freeze tool: `zapote/power-stage-120v/tools/build_source.py`

**Do not reuse `zapote/current-sense/tools/build_current_sense_source.py`.** It
copies the repo's canonical `elec/src`, which does not contain this unit.
Instead, base it on the Rev38 tool, which copied its own unit's source:

```sh
git show "archive/rev38-power-entry-2026-09-25:zapote/power-entry/passive-reva/protection/interface-integration-38/tools/build_source.py"
```

Write a new file with this behavior:

1. **Paths:**
   - `ROOT = Path(__file__).resolve().parents[1]` (= `zapote/power-stage-120v`)
   - `REPO = Path(__file__).resolve().parents[3]`
   - `sys.path.insert(0, str(REPO / "harness-lab"))`, then `import block_source`
   - `ENTRY_FILE = "elec/src/power_stage_120v.ato"`, `ENTRY_MODULE = "PowerStage120V"`
2. **Arguments:** one, the output directory. Refuse if it exists
   (`FileExistsError`).
3. **Stage the source:** create `output/elec`, then
   `shutil.copytree(ROOT/"elec"/"src", output/"elec"/"src")`. Write
   `output/ato.yaml` with `ato-version: 0.2.69` and the default build entry.
4. **Build:** `proc = block_source.run_atopile_build(output, ENTRY_FILE, ENTRY_MODULE)`.
   Write `stdout.txt` and `stderr.txt`.
5. **Receipt:** write `build-receipt.json` with schema
   `"temper.power-stage-120v.source-build.v1"`, `status`, `entry`,
   `returncode`, `"build_report_failed": "FAILED" in proc.stdout`,
   `"source_hashes": block_source.workspace_hashes(output)`, and the SHA-256 of
   this script.
6. **Gate, export, finalize:**
   - `block_source.gate_build(proc)` raises on failure.
   - `block_source.run_resolved_export(output, ENTRY_FILE, ENTRY_MODULE, output/"resolved-components.json")`
   - Set `status: "compiled-and-exported"` and `export_sha256`, then rewrite the receipt.

Smoke test:

```sh
cd zapote/power-stage-120v
python3 tools/build_source.py source-build-01
rustc --edition=2021 -O audit.rs -o /tmp/ps_audit
/tmp/ps_audit source-build-01/build/default.net source-build-01/build/default.csv source-build-01/resolved-components.json
# must print PASS
```

Then confirm the frozen copies still match. Compare
`source-build-01/build/default.net` with `frozen/default.net` after replacing
each file's absolute unit path with the literal text `UNIT`. They must be
byte-identical, and so must the CSVs. If they differ, stop: either the
source changed without re-freezing, or the build isn't reproducible.

### 1.5 Unit native wrapper: `zapote/power-stage-120v/tools/build_native.py`

Copy the shape of `zapote/gate-drive/tools/build_native.py` exactly (20 lines),
changing:
- `u = REPO / "zapote/power-stage-120v"`
- the source dir: `u / "source-build-01"`
- modules: `("PowerStage120V",)`; `entry_module="PowerStage120V"`;
  `entry_file="elec/src/power_stage_120v.ato"`
- `title="120 V Full-Bridge Induction Power Stage"`
- add `local_libraries=u / "libraries"`

Leave stackup application for Part 4. Running this now is **expected to fail**
at footprint vendoring, because Part 2 hasn't created the unit library yet. Run
it once and paste the error into the commit message as the expected
pre-Part-2 state.

### 1.6 Unit route tool: `zapote/power-stage-120v/tools/apply_routes.py`

Copy `zapote/gate-drive/tools/apply_routes.py` verbatim (15 lines). It
re-uses `zapote/rtd/apply_routes.py`. Only fix paths if the relative depth
differs, which it doesn't: both files are at `zapote/<unit>/tools/`.

## Acceptance checklist (all required)

- [ ] `harness-lab/{block_source,block_native,buck_native}.py` restored, plus README; `gen_repo_state --check` OK
- [ ] `temper-design-bundle` bridge functions present; `make extensions-check` fresh; Python import check prints `True`; `cargo test -p temper-design-bundle` passes
- [ ] No duplicate `wrap_pyfunction` names in `lib.rs`
- [ ] `tools/build_source.py` produces `source-build-01`, whose outputs the audit passes and whose netlist and CSV match `frozen/` after path normalization
- [ ] `tools/build_native.py` exists and fails *only* at footprint vendoring
- [ ] `tools/apply_routes.py` exists
- [ ] `cargo test --locked --manifest-path zapote/Cargo.toml --workspace` still 299/299
- [ ] One commit (or a few), then a PR titled `feat(power): native-bridge toolchain for power-stage-120v`

## Stop and ask if

- the design-bundle patch conflicts non-additively, or `make extensions` fails for a reason you can't trace to this patch
- a restored harness-lab module needs more than an import fix
- the smoke build's netlist differs from `frozen/`
