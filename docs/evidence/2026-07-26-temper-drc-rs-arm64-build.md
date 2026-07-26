# temper-drc-rs macOS arm64 build — investigation result

**Date:** 2026-07-26
**Crate:** `packages/temper-drc-rs`
**Platform:** macOS darwin 25.5.0, Apple Silicon (arm64), rustc 1.92.0, cargo 1.92.0,
Python 3.12.12 (Miniforge), maturin 1.14.1

## Summary

**The build does not currently fail in this worktree.** `cargo build`, `cargo build
--release`, `cargo test`, `maturin build`, wheel install, and a live Python import
that actually invokes the three isolation DRC rules all succeed cleanly, from a
fully clean `target/` directory, using only the committed `Cargo.lock`.

The task briefing states a prior control experiment found "the crate fails
identically UNMODIFIED on the current branch." That claim does not hold in this
worktree's checked-out history. Investigation (below) found the root cause it
was almost certainly describing — a `pyo3` 0.23/0.29 version split across the
crate's dependency graph — and found that this exact issue was already fixed by
commit `12a845e3` ("fix: migrate remaining pyo3 0.23→0.29 crates", 2026-07-24),
which is an ancestor of both this worktree's HEAD and of
`fix/forced-segment-fail-closed` (verified with
`git merge-base --is-ancestor 12a845e3 fix/forced-segment-fail-closed` → yes).

**No code change was made.** Per the task's own constraint ("If you cannot
verify something, write UNVERIFIED rather than guessing"), the correct action
when a described failure does not reproduce is to report that, not to invent a
change to justify a "fix." This document is evidence of that investigation.

## Falsifier (stated before running anything further)

> Diagnosis: the crate is not currently broken on this branch/worktree; the
> failure described in the task briefing was already fixed upstream by commit
> `12a845e3`. This is wrong if a clean `cargo build`, `cargo test`, or
> `maturin build` fails in this worktree, or if the built wheel fails to import
> into Python, or if the three isolation rules (`safety_isolation`,
> `routing_isolation_barrier`, `routing_isolation_slot`) error out when invoked
> through `temper_drc_rs.run_drc`.

**Result: the falsifier did not fire.** Every one of those steps succeeded (full
output below).

## Reproduction attempt (exact commands, exit codes measured without pipelines)

```
$ cd packages/temper-drc-rs
$ cargo build > out.txt 2>&1; echo "exit=$?"
exit=0
```

Full output (clean build, target/ did not exist beforehand — 27 crates compiled
from scratch including proc-macro2, pyo3, pyo3-ffi, geo, rstar):

```
   Compiling proc-macro2 v1.0.106
   ...
   Compiling pyo3-build-config v0.29.0
   Compiling pyo3-ffi v0.29.0
   Compiling pyo3 v0.29.0
   Compiling rstar v0.12.2
   ...
   Compiling pyo3-macros-backend v0.29.0
   Compiling pyo3-macros v0.29.0
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 8.09s
```

```
$ cargo build --release > out.txt 2>&1; echo "exit=$?"
exit=0

$ cargo test > out.txt 2>&1; echo "exit=$?"
exit=0
```

`cargo test` output tail:

```
running 49 tests
... (49 individual test lines, all "... ok")
test result: ok. 49 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

   Doc-tests temper_drc_rs
running 0 tests
test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

```
$ maturin build > out.txt 2>&1; echo "exit=$?"
exit=0
```

```
🐍 Found CPython 3.12 at /Users/bennet/Miniforge3/bin/python3
🔗 Found pyo3 bindings
📡 Using build options features from pyproject.toml
💻 Using `MACOSX_DEPLOYMENT_TARGET=11.0` for aarch64-apple-darwin by default
   Compiling pyo3-ffi v0.29.0
   Compiling pyo3 v0.29.0
   Compiling temper-drc-rs v0.1.0
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 3.82s
📦 Built wheel for CPython 3.12 to .../target/wheels/temper_drc_rs-0.1.0-cp312-cp312-macosx_11_0_arm64.whl
```

## Configuration checked and found correct (not the cause, contrary to the
## briefing's candidate list)

- `.cargo/config.toml` in `packages/temper-drc-rs/` has `-undefined
  dynamic_lookup` rustflags for **both** `[target.aarch64-apple-darwin]` and
  `[target.x86_64-apple-darwin]` — correctly covers the arm64 triple actually in
  use (`rustup show` confirms host = `stable-aarch64-apple-darwin`). Not a
  mistargeted-triple bug.
- `Cargo.toml` `[lib]` already has `crate-type = ["cdylib", "rlib"]`. Not a
  missing-crate-type bug.
- `Cargo.lock` (tracked in git, not gitignored — only `target/` is ignored)
  resolves a single, consistent `pyo3 0.29.0` throughout: `pyo3`,
  `pyo3-build-config`, `pyo3-ffi`, `pyo3-macros`, `pyo3-macros-backend` are all
  pinned to `0.29.0`. No version mismatch in the current lockfile.
- `pyproject.toml` requires Python `>=3.12`; the active interpreter
  (`/Users/bennet/Miniforge3/bin/python3`) is 3.12.12, and `.python-version` at
  repo root pins `3.12`. No interpreter/ABI mismatch.

## What the failure almost certainly was, and why it's gone

Commit `12a845e3` ("fix: migrate remaining pyo3 0.23→0.29 crates", authored
2026-07-24, already present in this worktree's history and in
`fix/forced-segment-fail-closed`) changed `packages/temper-drc-rs/Cargo.toml`:

```diff
-pyo3 = { version = "0.23", features = ["extension-module"] }
+pyo3 = { version = "0.29", features = ["extension-module"] }
```

and updated 17 call sites in `src/board_py_bridge.rs`, `src/constraints.rs`, and
`src/lib.rs` for pyo3 0.29's renamed/changed API surface:

- `val.downcast::<T>()` (returns `&Bound<'_, T>`, pyo3 ≤0.23) →
  `val.cast_into::<T>()` (returns `Bound<'_, T>` by value, pyo3 0.29)
- `PyObject` (a type alias that changed shape between pyo3 versions) →
  `Py<PyAny>`

The commit message states this "fixes pyo3-ffi native library conflict" — i.e.
before this fix, `temper-drc-rs` was pinned to `pyo3 0.23` while sibling crates
(`temper-py-bridge`, `temper-constraint-compiler`, `temper-quality-oracle`,
`temper-design-bundle`) had already moved to `0.29`. A per-crate `pyo3-ffi`
version split like that is a classic cause of the "multiple pyo3-ffi versions"
class of build/link failures pyo3 extension modules are prone to (each version
brings its own native symbol set; mixing them in a workspace or in processes
that load multiple extension modules causes duplicate-definition or
ABI-mismatch failures). This matches the briefing's build-failure framing far
better than the mistargeted-triple or missing-crate-type candidates, both of
which were checked and ruled out above.

**This fix is already merged and present on both this worktree's HEAD
(`ee9ba6ba...`) and on `fix/forced-segment-fail-closed` (`b259419f`)** —
confirmed via `git merge-base --is-ancestor 12a845e3 fix/forced-segment-fail-closed`
(exit 0 → yes).

**UNVERIFIED:** I did not personally observe the original raw compiler error
text (it predates this worktree's checked-out history and is not reproducible
here). The description above of "why it's gone" is reconstructed from the
commit diff and message, not from a captured failing build log. Treat the
specific historical error text as unverified; the current-state build/test/
import results above are directly measured, not inferred.

## Verification that the three isolation checks actually run (not just registered)

All three rules are registered in `src/rules/mod.rs` (`IsolationCheck`,
`IsolationBarrierCheck`, `IsolationSlotCheck`). To confirm they are actually
*callable* through the compiled Python extension (not just present in source),
the built wheel was installed into an isolated target directory and invoked
directly:

```
$ pip install --target drc_install --no-deps --force-reinstall \
    target/wheels/temper_drc_rs-0.1.0-cp312-cp312-macosx_11_0_arm64.whl
Successfully installed temper-drc-rs-0.1.0

$ PYTHONPATH=drc_install python3 -c "
import temper_drc_rs
print(dir(temper_drc_rs))
"
['run_drc', 'temper_drc_rs']
```

Then, with a minimal K1-schema board (`U1` on net_class `mains` sitting inside a
zone named `iso_gutter` constrained to net_class `mains`; `U2` on `signal`
outside it) and constraints dict matching `_constraints_to_dict`'s zone schema
(`{name, bounds, net_classes, components}`):

```
$ PYTHONPATH=drc_install python3 run_isolation_checks.py
OK  safety_isolation: 1 violation(s) -> [{'severity': 'ERROR', 'code': 'SAF_ISO_001',
    'message': "Safety violation: Component U1 (mains) is in isolation zone 'iso_gutter'",
    'category': 'safety', 'check_name': 'safety_isolation', 'affected_items': ['U1'],
    'location': {'x': 10.0, 'y': 10.0, 'layer': 'F.Cu'},
    'details': {'component_class': 'mains', 'zone_name': 'iso_gutter'}}]
OK  routing_isolation_barrier: 0 violation(s) -> []
OK  routing_isolation_slot: 0 violation(s) -> []
```

`safety_isolation` correctly flagged a real violation (positive evidence it
executes real logic, not a no-op stub); `routing_isolation_barrier` and
`routing_isolation_slot` executed without error and returned no violations for
this input (consistent with the test board having no barrier/slot geometry to
evaluate — not proof of their internal correctness, only proof they are
reachable and don't crash/error through the Python boundary).

Note: an earlier attempt using the `zones` key inside the *board* dict (as
opposed to the *constraints* dict) failed with `ValueError: board
deserialization error: ValueError: missing required key: net` — the board
dict's `zones` key is parsed by `board_py_bridge.rs::parse_zones_from_dict` as
**copper zones** (`{net, layer, polygon}`), which is a different schema from
the **isolation/keepout zones** the three isolation rules read from
`constraints.zones` (`{name, bounds, net_classes, components}`). This is a
pre-existing schema-naming collision between two unrelated concepts that both
use the key `"zones"` at different nesting levels. It is not a build failure
and out of scope for this task, but is worth flagging separately since it's an
easy foot-gun for callers of `run_drc`.

## Are the three isolation checks unblocked?

**Yes, and this was directly measured, not just believed.** All three
(`safety_isolation`, `routing_isolation_barrier`, `routing_isolation_slot`) were
invoked through the actual compiled `.so`/wheel via
`temper_drc_rs.run_drc(board, constraints, check_names=[...])` and executed to
completion, with `safety_isolation` producing a correct, real violation for a
deliberately-crafted input. They were not merely "believed" to work — they were
run.

## What remains UNVERIFIED

- The exact original compiler/linker error text from the control experiment
  referenced in the task briefing — not reproducible in this worktree's history,
  not captured anywhere I could find, reconstructed only from the fix commit's
  diff/message.
- Whether the O(n²) Python `verify_clearance` port into Rust exists yet in this
  crate — grep found no `verify_clearance` symbol inside
  `packages/temper-drc-rs/src`; the Python version lives in
  `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py`. This
  crate does have a `rules::drc::clearance` module with its own clearance
  check, but I did not verify it is a complete drop-in replacement for the
  Python `verify_clearance` or that it has been benchmarked against the 27
  min/9.2 GB figure cited in the task. That is a separate, larger piece of work
  not attempted here.
- Whether `fix/forced-segment-fail-closed` (the named base branch) itself
  builds cleanly end-to-end beyond this one crate — only `temper-drc-rs` was in
  scope for this task.

## Commit

No source change was made to `temper-drc-rs` — none was needed. This document
is committed alone.
