<!-- provenance: branch feat/leaf-compute-rust-completion, worktree
/tmp/opencode/wt-suite-repair, from origin/main at 8f21d2725 (#1175). Companion
to docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md
(Phase E batches E4/E5, which produced the shim state this document classifies)
and docs/plans/2026-08-12-002-feat-router-orchestration-rust-plan.md (the SAT /
solver-orchestration side — deliberately NOT re-scoped here). No pcb/** modified.
All line counts measured on this branch's working tree. The classification was
corrected in-session after the first draft: measuring the two "delete-ready"
candidates surfaced a load-bearing side effect (`topology_extraction`) and a
deliberate keep-Python seam (`net_batching`). The corrections are marked
[measured] inline. -->
# Python leaf compute to Rust: completion options, and the landing sequence

**Status:** scoping/decision only. No `pcb/**`, no production `.py` or `.rs`
changed by this document itself. The first draft of this document recommended a
"delete phase first" sequence; measuring the candidates during this session
refuted that recommendation's premises. The corrected picture, options, and
landing sequence are below.

## Recap of the state this brainstorm is scoped against

The Rust `RouterPipeline` (temper-orchestration) drives stage *sequencing* and
calls Python stage call-backs for the leaf compute
(`_pipeline_core.py`). The geometry/analysis leaf compute lives in
`router_v6/` and has been migrating module-by-module since Phase E (plan
2026-08-09-001). Measuring the current state module by module on this branch:

| Module | Lines | Rust home | State |
|---|---|---|---|
| `topology_extraction.py` | 53 | `temper-design-bundle` `topology_extraction_contracts` (PathGraph, NetTopology, TopologyGraph) | Re-export + **load-bearing compat side effect** — `_install_dataclass_fields(..., module=__name__)` repoints the pyclasses' `__module__` so `typing.get_type_hints` and pickling resolve against this module's globals [measured]. **Not deletable without relocating that side effect.** |
| `channel_mapping.py` | 315 | `temper-orchestration` `channel_mapping.rs` + `temper-geometry` kernels | Retained types (`ChannelPath`, `ChannelMapping`) + FFI delegation (`map_topology_to_channels` / `expand_channel_path_terminals` / `fallback_channel_path` / `_assign_layer`) + 4 leaf-kernel wrappers. Only genuinely-dead member is `_LAYER_ENUM_TO_KICAD` (6 lines). Not a deletable shim — it owns the in-process data types the A* heuristics consume. |
| `channel_widths.py` | 700 | `temper-orchestration` `channel_mapping.rs` (`run_channel_widths_edt`) | **Partial** — the EDT rasterised-grid prep (numpy interior mask / bounds) is still Python. The one clear porting gap in the Stage-2/4 set. |
| `channel_skeleton.py` | 666 | `temper-design-bundle` `SkeletonGraph` + `temper-geometry` | **Partial** — medial-axis transform is still Python (shapely/numpy). A real porting gap. |
| `bundle_analyzer.py` | 546 | `temper-geometry` `bundle_analyzer` kernel (GEOS seam) | **Partial** — net-partitioning orchestration (control flow over the already-Rust GEOS seam) is still Python. A real porting gap. |
| `net_batching.py` | 1283 | `temper-rust-router-core` `net_batching.rs` (E5) | **Migrated, keep-Python seam by design** — `order_nets`/`chunk_indices`/`shrink_channel_widths`/`consume_capacity` are Rust (E5); the subprocess-per-batch driver stays Python as a documented non-goal ("No subprocess-wrapper migration", argued in the shim header and VERIFICATION.md) [measured]. **No port remains here.** |

## What measuring changed (corrections to the first draft)

1. **[measured] `topology_extraction.py` is not a pure re-export shim.** Its
   `_install_dataclass_fields(NetTopology/TopologyGraph, module=__name__)` calls
   are the load-bearing mechanism that makes the pyclasses behave like
   dataclasses (`dataclasses.replace()`/`fields()` read genuine
   `__dataclass_fields__`) and that repoints `__module__` so string
   annotations (`"PathGraph | None"`, `"dict[str, NetTopology]"`) resolve and
   pickles unpickle. Deleting the module orphans both. Deletion requires first
   relocating the side effect to a home whose globals hold all three names and
   that is guaranteed imported before first use — which is the same module, or
   a rename of it. That is a rename, not a deletion.
2. **[measured] `channel_mapping.py` is not a deletable shim.** It owns
   `ChannelPath`/`ChannelMapping`, the in-process representation the A*
   heuristics, terminal-tree execution, and the Stage-4 driver consume. Its
   "deletion" would be a module rename with one 6-line dead-dict removal
   across ~32 import sites — churn, not migration.
3. **[measured] the differential tests are load-bearing Rust pins, not
   degenerate wrappers.** `test_channel_ops_rust_differential.py` carries an
   anti-vacuity assertion that each shim function binds to a
   `temper_orchestration` pyfunction (`__module__`/import binding) and pins the
   **Rust orchestration** (`run_channel_mapping`, `run_channel_widths_edt`, ...)
   against the verbatim pre-migration oracle. `test_channel_mapping_rust_differential.py`
   pins the leaf-kernel wrappers (which delegate to `temper-geometry` kernels)
   against oracles copied from the pre-migration module. Retiring them on a
   "delete phase" premise would **weaken** the Rust regression story — the
   exact opposite of the branch's originating goal. They stay, and any future
   shim change repoints them, never retires them.
4. **[measured] "port to `temper-rust-router-core`" is already done for the
   one module that belongs there.** `net_batching.rs` covers the portable
   batch-loop primitives; the Python remainder is the deliberately-unmigrated
   subprocess driver. The other five modules' Rust homes are
   `temper-design-bundle` / `temper-geometry` / `temper-orchestration`, and
   re-porting them into `temper-rust-router-core` would be duplication, not
   migration.

## The classification, corrected

Following the temper-drc precedent
(`docs/solutions/architecture-patterns/temper-drc-rust-migration-shim-then-delete-2026-08-03.md`),
a shim's endgame is deletion — but only when the shim is pure delegation with
no remaining leaf compute **and** no retained in-process data type. Neither
delete-ready candidate survives that test:

1. **Delete-ready now:** *none.* The closest is `topology_extraction.py`, and
   it carries the compat side effect ([measured] correction 1).
2. **One kernel port away from deletion:** `channel_widths.py` (EDT grid prep,
   numpy → `temper-geometry`) and `channel_skeleton.py` (medial-axis, shapely →
   `temper-geometry`). These are the two genuinely-portable pieces left in the
   Stage-2/4 set.
3. **One orchestration port away from deletion:** `bundle_analyzer.py` (the
   GEOS seam is Rust; the net-partitioning control flow is Python).
4. **No port remains; a deliberate keep-Python seam:** `net_batching.py`'s
   subprocess driver ([measured] correction 4).
5. **Retained permanent surface:** `channel_mapping.py`'s types + delegation,
   and `topology_extraction.py`'s compat installation (unless the relocation in
   U5 is taken). These are the in-process API the Rust orchestration returns
   into; they are the *end-state shape*, not a migration artifact.
6. **Test-surface consequence, stated plainly:** no differential test is
   retired by any of the above. They pin Rust-vs-pre-migration-oracle behavior
   ([measured] correction 3); they are the coverage the ports are measured
   against, not the coverage being removed.

## Option A: port the three real gaps as additive units (recommended)

**Shape:** port EDT grid prep, medial-axis, and bundle partitioning into
`temper-geometry` kernels with differential tests (the established pattern:
Rust kernel + `_*_py_oracle.py` content-hash pin + bit-exact differential).
No shim is deleted until a unit's Python compute is fully absorbed; the
retained-type modules stay as the permanent API. `channel_mapping`'s dead
`_LAYER_ENUM_TO_KICAD` rides along as a trivial cleanup.

**Why first:** these are the only three pieces of Python leaf compute that
are actually left to port. Everything else is either already Rust (orchestration,
kernels, batching primitives) or deliberately Python (subprocess driver, retained
types). This option does the remaining real work in dependency order, additive
and low-risk, against the differential-test backstop that already exists.

**Cost:** three Rust-kernel units, each with a geometry-parity spike before it.
EDT and medial-axis are the geometrically harder two; bundle partitioning is
control-flow work over an existing kernel. None of the three is a one-session
change.

## Option B: delete first, port later

**Shape:** the first draft's plan — delete `topology_extraction.py` and
`channel_mapping.py` now, repoint importers, relocate dataclasses, retire the
differential tests.

**Why rejected after measuring:** both modules are non-deletable as classified
([measured] corrections 1 and 2), and the test retirements would remove
Rust-oracle pins ([measured] correction 3). The option's premise — that
shrink-the-Python-first is free — is false: the only actual deletion is a
rename plus a 6-line dead-dict removal, bought with ~32 repointed import sites
and the risk of orphaning the compat `__module__` repoint.

## Option C: stop here; treat the current shape as the end state

**Shape:** declare the leaf-compute migration complete, keep the differential
suite as-is, and skip the three remaining ports.

**Why rejected:** the EDT grid prep, medial-axis, and bundle-partitioning
control flow are still numpy/shapely/Python on the production path — genuine
migration remnants, not deliberate seams (unlike the subprocess driver). They
are the reason scipy/shapely remain in the dependency set despite the 2026-08
migration-reversal sweep. Leaving them is leaving the migration half-finished
in exactly the three places the sweep could not close.

## Recommendation and landing sequence

**Option A.** The units, in order:

1. **U1 (this document):** correct the classification from measurement. The
   "delete phase" premise is withdrawn; the three real ports below are the
   remaining scope.
2. **U2:** port `channel_widths.py`'s EDT rasterised-grid prep (numpy interior
   mask / bounds → a `temper-geometry` kernel), differential-tested bit-exact
   against the pinned oracle. This closes the one gap that keeps numpy on the
   Stage-2 path.
3. **U3:** port `channel_skeleton.py`'s medial-axis transform (shapely →
   `temper-geometry` kernel), differential-tested. Closes the shapely seam.
4. **U4:** port `bundle_analyzer.py`'s net-partitioning orchestration
   (control flow over the already-Rust GEOS seam), differential-tested.
5. **U5:** decide `topology_extraction`'s compat side effect: either relocate
   the `_install_dataclass_fields(module=...)` installation to a stable home so
   the module can be deleted (requires re-validating `get_type_hints` and
   pickling against any persisted object), or formally accept the module as the
   permanent compat seam and document it as such. Either outcome is fine; the
   current state — an un-documented, incidental seam — is not.
6. **U6:** trivial cleanups that ride along (drop `_LAYER_ENUM_TO_KICAD`);
   sweep remaining `router_v6/` stage call-backs (escape-via generation, DFM
   checks, Stage-0 marshalling) for the same classification.

U2-U6 are filed as follow-up tickets from this document, not executed inline.
