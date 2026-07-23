# Temper Architecture

## 1. Dependency Graph

The `temper_placer` package import graph is now a **directed acyclic graph (DAG)**.
It was previously a **14-module static import cycle** that entangled the monolith.
The cycle was dismantled through sequential refactorings: fixing wrong-target imports
(#118, #119), lifting shared types to new zero-dependency modules (#120, #208,
#272), converting functional imports to lazy/TYPE_CHECKING (#183, #208, #272),
and extracting geometry to Rust (#273).

The `import-linter-baseline.yaml` is **empty** — zero unresolved violations. The
baseline is ratcheted via CI and only shrinks.

Remaining cross-module imports are either:
- `TYPE_CHECKING`-guarded (type annotations only, zero runtime cost)
- Lazy runtime imports (deferred until first use)
- Valid orchestration edges that go through public `__init__.py` interfaces

The `.importlinter` configuration enforces two main contracts:
- `core-isolated-from-router-v6`: core/ must not import from router_v6/
- `*-public-interface-only`: external packages must import only via public
  `__init__.py` exports

## 2. Rust Crate Map

The Rust layer extracts performance-critical and cycle-entangled modules from
Python. Each `*-core` crate is a pure-Rust library (`rlib`); the matching
PyO3 crate wraps it for use from `temper_placer`.

| Rust crate | Replaces | Language | Binding |
|---|---|---|---|
| `temper-geometry-core` | `temper_placer/geometry/` (types) | Rust (rlib) | — |
| `temper-geometry` | 8 geometry submodules (primitives, polygon, sdf, smooth, transform, overlap, projections, drc_inflate) | Rust + PyO3 | `temper_geometry` |
| `temper-dsn-core` | DSN (Specctra) format parsing | Rust (rlib) | — |
| `temper-dsn` | DSN Python module | Rust + PyO3 | `temper_dsn` |
| `temper-ipc-core` | IPC-2221 trace width / clearance | Rust (rlib) | — |
| `temper-ipc` | IPC Python module | Rust + PyO3 | `temper_ipc` |
| `temper-pcl-ir` | Shared PCL IR types | Rust (rlib) | — |
| `temper-constraints` | Constraint loss computation | Rust + PyO3 | `temper_constraints` |
| `temper-constraint-compiler` | PCL -> SAT ISA lowering compiler | Rust + PyO3 | `temper_constraint_compiler` |
| `temper-drc-rs` | DRC engine (geo + rstar) | Rust + PyO3 | `temper_drc_rs` |
| `temper-quality-oracle` | Six-layer quality pipeline | Rust + PyO3 | `temper_quality_oracle` |
| `temper-rust-router-core` | SAT solver, topology/loop extraction | Rust (rlib) | — |
| `temper-rust-router` | Router V6 topo stage | Rust + PyO3 | `temper_rust_router` |
| `temper-design-bundle` | Atopile/PCL provenance boundary | Rust + PyO3 | `temper_design_bundle_python` |
| `temper-py-bridge` | Shared PyO3 dict extractors | Rust (rlib) | — |
| `temper-py-bridge-derive` | `FromPyDict` / `ToPyDict` derive | Rust (proc-macro) | — |
| `temper-io-types` | KiCad IO types + golden serializers | Rust + PyO3 | `temper_io_types` |

The `temper-io-types` crate is on branch `feat/io-port-final`; the remaining
16 crates are on `main`.

## 3. Cycle-Breaking Pattern

Three techniques are applied in escalating order of effort. They form a
reusable, sequenced playbook:

### Tier 1 — Lift Types to a Shared Module

Move shared types into a new zero-dependency module that sits below both
former importers in the DAG. Key examples: `_constraint_types/` (34 types
lifted from `io/config_loader`, severed `constraints -> io`), `core/geometry_types.py`
(Point, Pad, Track, Via), `io/_kicad_types.py` (ParseResult, ViaData), and
`_version.py` (root version string, severed `cli -> temper_placer` root import).

### Tier 2 — Lazy / TYPE_CHECKING Imports

Convert top-level `import` statements to runtime-lazy (import inside function
body) or `TYPE_CHECKING`-guarded (annotation-only). Removes the edge from the
static cycle detector. Key examples: 6 geometry imports in
`deterministic/connectivity_validation.py` converted to lazy (#272), runtime
`Severity` import replaced with string comparison (#119), `spice <-> challenger`
CornerResult moved under TYPE_CHECKING (#183).

### Tier 3 — Extract to Rust

Port the entangled module to a Rust crate with pyo3 bindings. The Rust crate
has zero Python import dependencies, eliminating the cycle edge entirely.
Examples: `temper_geometry` replaces `temper_placer/geometry/` (severed
`geometry -> core` edge, #273), `temper-io-types` replaces io type modules
(on branch `feat/io-port-final`), `temper-drc-rs` replaces Python DRC,
`temper-constraints` replaces runtime constraint loss computation.

## 4. Current Crate Inventory

### Rust crates (17 on main, 1 on branch)

| Package | Language | PyO3 module | Description |
|---|---|---|---|
| `temper-geometry-core` | Rust | — | Shared geometry data types |
| `temper-geometry` | Rust+Py | `temper_geometry` | PyO3 wrapper for geometry-core |
| `temper-dsn-core` | Rust | — | DSN (Specctra) format utilities |
| `temper-dsn` | Rust+Py | `temper_dsn` | PyO3 wrapper for dsn-core |
| `temper-ipc-core` | Rust | — | IPC-2221 trace calculations |
| `temper-ipc` | Rust+Py | `temper_ipc` | PyO3 wrapper for ipc-core |
| `temper-pcl-ir` | Rust | — | Shared typed PCL IR |
| `temper-constraints` | Rust+Py | `temper_constraints` | PCL constraint loss engine |
| `temper-constraint-compiler` | Rust+Py | `temper_constraint_compiler` | PCL -> SAT ISA compiler |
| `temper-drc-rs` | Rust+Py | `temper_drc_rs` | DRC engine (geo + rstar) |
| `temper-quality-oracle` | Rust+Py | `temper_quality_oracle` | Six-layer quality pipeline |
| `temper-rust-router-core` | Rust | — | SAT solver + topo extraction |
| `temper-rust-router` | Rust+Py | `temper_rust_router` | Router V6 pyo3 wrapper |
| `temper-design-bundle` | Rust+Py | `temper_design_bundle_python` | Atopile/PCL provenance boundary |
| `temper-py-bridge` | Rust | — | Shared PyO3 extractors |
| `temper-py-bridge-derive` | Rust | — | FromPyDict/ToPyDict proc-macro |
| `temper-io-types` | Rust+Py | `temper_io_types` | KiCad IO types + serializers (branch) |

### Pure Python packages (4)

| Package | Description |
|---|---|
| `temper-placer` | CP-SAT PCB placement optimizer (monolith) |
| `temper-workflow` | GPBM workflow orchestration |
| `temper-testing` | Testing toolkit for numerical optimization + placement verification |
| `temper-validation` | Ground truth comparison for PCB placement validation |

### Crate dependency graph (Rust)

```
temper-pcl-ir  (no deps)
  ├── temper-constraints
  └── temper-design-bundle

temper-geometry-core  (no deps)
  └── temper-geometry

temper-dsn-core  (no deps)
  └── temper-dsn

temper-ipc-core  (no deps)
  └── temper-ipc

temper-rust-router-core  (no deps)
  ├── temper-rust-router
  └── temper-constraint-compiler

temper-py-bridge-derive  (no deps)
  └── temper-py-bridge
```
