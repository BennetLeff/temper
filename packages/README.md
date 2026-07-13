<!-- When adding or removing a package, update this table. -->

The `packages/` directory contains the temper EDA pipeline — placement, routing, DRC, geometry, constraints, and supporting tooling.

| Package | Purpose | Language | Rust extraction |
|---------|---------|----------|-----------------|
| `temper-constraint-compiler` | Constraint lowering compiler — compiles PCL designer-level constraints through a type lattice and multi-tier desugaring into SAT constraint ISA | Python + Rust | done |
| `temper-design-bundle` | Validated, provenance-carrying Atopile and PCL design boundary | Python + Rust | partial |
| `temper-drc-rs` | Rust DRC engine — PCB design rule checks with geo + rstar spatial indexing | Python + Rust | done |
| `temper-dsn` | DSN (Specctra) format utilities for temper PCB placement | Python + Rust | done |
| `temper-geometry` | 2D geometry math functions for temper PCB placement | Python + Rust | done |
| `temper-geometry-core` | Shared geometry data types for temper | Python + Rust | done |
| `temper-ipc` | IPC standard calculations for PCB design (current capacity, trace width) | Python + Rust | done |
| `temper-pcl-ir` | Shared typed PCL intermediate representation | Python + Rust | done |
| `temper-placer` | CP-SAT-based PCB placement optimizer for the Temper induction cooker | Python | N/A |
| `temper-quality-oracle` | Typed quality oracle for PCB placement — implements the full six-layer quality pipeline as a pure Rust function | Python + Rust | done |
| `temper-rust-router` | Router V6 topology stage — pyo3 Python extension (wraps temper-rust-router-core) | Python + Rust | done |
| `temper-rust-router-core` | Router V6 topology stage — pure-Rust core (SAT solver, topology extraction, loop extraction) | Python + Rust | done |
| `temper-testing` | Testing toolkit for numerical optimization and placement verification | Python | N/A |
| `temper-tools` | Utility tools for Temper development | Python | N/A |
| `temper-validation` | Ground truth comparison package for PCB placement validation | Python | N/A |
| `temper-workflow` | GPBM workflow orchestration for Temper development | Python | N/A |

Packages with a `-core` suffix (`temper-geometry-core`, `temper-rust-router-core`) are pure-Rust type crates with zero logic — the corresponding non-core package (`temper-geometry`, `temper-rust-router`) wraps them with Python bindings and adds computation.
