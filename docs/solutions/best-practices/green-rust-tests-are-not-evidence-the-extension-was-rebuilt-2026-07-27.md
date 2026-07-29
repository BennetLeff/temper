---
title: "Green Rust tests are not evidence the Python extension was rebuilt"
date: "2026-07-27"
category: best-practices
module: ci_infrastructure
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a Rust crate is exposed to Python via pyo3/maturin as a cdylib, alongside a separately-tested rlib"
  - "a CI or local workflow reports a Rust test suite as green and treats that as proof the installed Python extension reflects current source"
  - "a build tool (maturin, uv, pip) prints a success message ('Installed ... as editable', 'Uninstalled/Installed N packages') after a develop/sync step"
  - "designing a freshness/presence gate for a compiled artifact that a separate tool installs into a Python environment"
  - "chaining `uv run <build-tool>` with any later `uv run <anything>` for a package uv itself manages as a workspace/path dependency"
tags:
  - stale-compiled-extension
  - pyo3
  - maturin
  - uv-auto-sync
  - green-tests-wrong-artifact
  - build-tool-success-message
  - fail-closed-gate
---

# Green Rust tests are not evidence the Python extension was rebuilt

## Context

Commit `02e907b9` fixed a missing `.cargo/config.toml`: on macOS, every
pyo3 `cdylib` in this repo failed to link (`ld: symbol(s) not found for
architecture arm64`, `__Py_TrueStruct`) because the `extension-module`
feature deliberately omits libpython, and Apple's linker rejects that
without `-undefined dynamic_lookup`. The mechanism that made this
dangerous rather than merely annoying: `cargo build`/`cargo test` build
the `rlib` half of the crate and link libpython normally, so they were
completely unaffected. `temper-drc-rs` reported 49/49 and `router-core`
101/101, green, while every installed `.so` in `.venv` sat frozen at its
last successful build. `temper_io_types.cpython-312-darwin.so` was dated
three days stale and did not contain `ConfigBoardMismatchError`, a symbol
its source had already registered — confirmed with `strings`, 2
occurrences in a fresh build, 0 in the installed one. Two pytest modules
failed to *collect* as a result: reported as an error line, not a failure
count, and easy to scroll past in a CI summary that only headlines
pass/fail totals.

Building the CI gate meant to catch this
(`scripts/check_stale_extensions.py`,
`docs/evidence/2026-07-27-stale-extension-gate.md`) surfaced a second,
independent instance of the same shape while testing the first: `uv run
maturin develop --release --manifest-path packages/temper-io-types/Cargo.toml`
ran to completion and printed `Installed temper-io-types-0.1.0`; a
`stat`/`md5` of the installed `.so` the instant after confirmed it was
genuinely fresh and byte-identical to the freshly-compiled `target/release`
artifact. Running `uv run python -c "pass"` — nothing, not even touching
`temper_io_types` — immediately reverted it: `uv` printed `Uninstalled 1
package ... Installed 1 package` and silently reinstalled the OLD wheel
from its own build cache, because `uv run <cmd>` performs an implicit
environment sync before running anything, and `temper-io-types` is
declared as a workspace/path dependency of the root project. Two
completely different tools (`maturin`, `uv`), two different success
messages, one silently-reverted artifact.

## Guidance

**A test suite (or a build tool's stdout) is evidence about the code path
it actually executed, not about every artifact derived from the same
source tree.** For a pyo3 crate specifically:

1. `cargo test`/`cargo build` prove the `rlib` half compiles and its logic
   is correct. They prove **nothing** about the `cdylib` half's linkage,
   and nothing at all about whether the compiled `.so` currently sitting
   in an installed Python environment matches current source — a
   completely separate artifact, produced by a completely separate build
   invocation (`maturin develop`/`maturin build`), that no `cargo`
   invocation ever touches.
2. A build tool's own success message is not proof its target artifact was
   replaced. This repo now has two independently-verified counterexamples:
   `maturin develop`'s "Installed ... as editable" while a stale `.so`
   stayed in place (the original incident), and `uv run`'s implicit
   auto-sync silently reinstalling a stale cached wheel over a
   genuinely-just-rebuilt one seconds later (discovered building the
   fix). Trust the filesystem, not the log line: stat the actual installed
   artifact and compare it against source, independently, every time.
3. When a tool wraps another tool with its own environment-management
   layer (`uv run` wrapping `maturin`), assume the wrapper can silently
   undo what the wrapped tool just did, unless proven otherwise. Here,
   `uv run --no-sync <cmd>` is the escape hatch; the general pattern is
   "know which of the two tools owns the artifact you just changed, and
   don't let the other one 'helpfully' resync it out from under you."
4. A freshness gate for a compiled artifact must locate and stat the real
   binary, not a wrapper. maturin's default packaging generates
   `<module>/__init__.py` (`from .<module> import *`) alongside
   `<module>/<module>.cpython-*.so` — the wrapper is regenerated on every
   build and can look fresh even when the real `.so` beside it was not
   replaced. Resolve past it.

## Update, 2026-07-27 (later the same day): the gate's first real run, and a third recurrence of the same reversion

`scripts/check_stale_extensions.py` merged, then ran against a clean tree
for the first time: **exit 3, 10 crates discovered, 7 stale**
(`docs/evidence/2026-07-27-stale-extension-first-run.md`). This was not a
backlog of housekeeping — two of the seven sat on the routing hot path:

| Crate | Installed | Source moved | Stale by |
|---|---|---|---|
| `temper_rust_router` | 2026-06-29 | 2026-07-27 | **28.2 days** |
| `temper_constraint_compiler` | 2026-07-06 | 2026-07-27 | **21.0 days** |

`temper_rust_router` is imported directly on the router's critical path
(`router_v6/_pipeline_route.py:289,310,405` —
`solve_topology_rust_bundled`, `solve_topology_rust`, `audit_result`), and
`temper_constraint_compiler`'s staleness traced to a same-day edit in
`packages/temper-rust-router-core/src/combinator/rewrite.rs`
(`cap_infos.iter().find(...)` → `cap_infos.get(orig_idx)`) that was
therefore **never in the binary any Python process that day had imported**.
This called into question, and required re-measurement of, the day's own
38.5% completion figure, its iteration-cap sweep, and its determinism
runs — all of which exercised `solve_topology_rust`. What did *not* need
re-checking: the fail-closed argument for the 45 unrouted nets, because
`_allow_forced_segments()`'s hard-coded `False` lives in
`_astar_reconstruct.py`, pure Python, unaffected by any extension's
staleness.

The same investigation also caught a **third, independent instance** of
the `uv run` auto-sync reversion this doc already documents twice above
(the "Installed" message that lied, and the immediate `uv run python -c
"pass"` clobber): after the falsifier sequence had completed and every
gate had re-verified green, a later, unrelated verification pass reported
`temper-io-types` STALE *again*. Investigation found the installed `.so`'s
content was correct (md5-identical to the freshly rebuilt artifact — a
source edit had been reverted, and Rust compilation is deterministic, so
recompiling the reverted source reproduced the original binary
byte-for-byte) but its **mtime never advanced** past its very first build,
because some layer of `uv`'s content-addressed build cache reused the
existing file rather than truly overwriting it once the content hash
matched something already cached
(`docs/evidence/2026-07-27-stale-extension-gate.md`). Three independent
reversion mechanisms in one day — a wrapping tool's own auto-sync, and now
a content-addressed cache short-circuiting a real rebuild — both hitting
the same crate, both invisible to anything short of an independent
mtime/hash comparison against source.

Two independent failures had to combine to hide a month of accumulated
staleness in the first place: the macOS link failure (no
`.cargo/config.toml`) meant the seven crates' `cdylib` halves silently
could not be rebuilt at all, and `cargo test` linking libpython normally
meant their `rlib` test suites stayed green throughout, giving no signal
that anything was wrong. All seven were rebuilt once found; the gate now
exits 0 and is wired into CI so a month-long accumulation cannot recur
silently.

## Why This Matters

The Rust-suite-green signal and the Python-import-succeeds signal are both
real, both necessary, and neither is sufficient — each observes a
different artifact, and the gap between them is exactly where this
project lost two test modules silently. A gate that only re-runs `cargo
test` or only re-imports the module (without comparing its build time to
its own source) inherits the same blind spot the original incident
exploited. The `uv run` auto-sync finding generalizes the lesson further:
even a gate that *does* correctly stat the real artifact needs to be
invoked in a way that doesn't let a wrapping tool quietly swap that
artifact back to a stale one immediately beforehand.

## When to Apply

- Any crate built with `crate-type = ["cdylib", "rlib"]` and consumed from
  both `cargo test` and a Python interpreter.
- Any workflow where a build step (`maturin develop`, `pip install -e`,
  similar) and a later "just run the thing" step (`uv run`, `poetry run`,
  a wrapped `pytest` invocation) are separate shell invocations — verify
  the second one doesn't own a competing installation path for the same
  package.
- Writing or reviewing any freshness/presence gate for a compiled artifact
  installed into a language runtime by a separate build tool: locate the
  real binary independently; never trust the build tool's own report of
  success.

## Examples

```
# WRONG -- treats a green Rust suite as proof the Python extension is current
$ cargo test --manifest-path packages/temper-io-types/Cargo.toml   # 49/49, green
$ uv run python -c "import temper_io_types"                        # imports fine
# Neither line says anything about whether the installed .so's BUILD DATE
# postdates lib.rs's last edit. Both can be true while the extension is stale.

# WRONG -- trusts the build tool's own success message
$ uv run maturin develop --release --manifest-path packages/temper-io-types/Cargo.toml
🛠 Installed temper-io-types-0.1.0        # <- not proof; verify independently
$ uv run python -c "pass"                 # <- can silently revert the install above
Uninstalled 1 package in 0.72ms
Installed 1 package in 1ms

# RIGHT -- verify with --no-sync, then independently stat the real artifact
$ uv run maturin develop --release --manifest-path packages/temper-io-types/Cargo.toml
$ uv run --no-sync python scripts/check_stale_extensions.py
# resolves past temper_io_types/__init__.py to the real
# temper_io_types.cpython-*.so, stats it, compares against
# max(mtime) over src/**/*.rs + Cargo.toml + local path deps
```

## Related

- `scripts/check_stale_extensions.py` — the gate this incident produced:
  fail-closed freshness/presence check across every pyo3/maturin extension
  crate in the repo, never a vacuous pass on zero crates discovered.
- `docs/evidence/2026-07-27-stale-extension-gate.md` — full falsifier
  demonstration (FAIL on a reconstructed staleness, PASS after a real
  rebuild) plus the `uv run` auto-sync finding and the third,
  content-addressed-cache reversion in detail.
- `docs/evidence/2026-07-27-stale-extension-first-run.md` — the gate's
  first run against a clean tree: 7 of 10 crates stale, including
  `temper_rust_router` at 28.2 days on the routing hot path, and what that
  called into question about the same day's own routing measurements.
- `scripts/check_rust_drc_presence.py` — the narrower, symbol-diff
  precursor gate for `temper_drc_rs` specifically (2026-07-26), which
  established the `TEMPER_REQUIRE_*`-env-var optional/required convention
  this gate's `TEMPER_REQUIRE_FRESH_EXTENSIONS` mirrors.
- `docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md` and
  `gate-neutering-mechanisms-2026-07-26.md` — sibling catalog of ways a
  gate can exist, run, and still not catch its target defect; this
  incident is a distinct shape (correct gate, wrong artifact) rather than
  a scoping or wiring gap.
