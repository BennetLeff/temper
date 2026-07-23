# CI base image: pre-installed system dependencies for temper workflows
# Rebuilt when lock files change; versioned by uv.lock + Cargo.lock hash
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# System packages: Python 3.12, Rust build deps, ngspice
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git \
    python3.12 python3.12-dev python3.12-venv \
    build-essential cmake pkg-config \
    libclang-dev \
    patchelf \
    ngspice \
    && rm -rf /var/lib/apt/lists/*

# KiCad (large package, separate layer for caching)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends software-properties-common \
    && add-apt-repository -y ppa:kicad/kicad-10.0-releases \
    && apt-get update && apt-get install -y --no-install-recommends kicad \
    && rm -rf /var/lib/apt/lists/*

# Rust toolchain (stable, minimal profile)
ENV RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal \
    && /root/.cargo/bin/rustup component add clippy
ENV PATH="/root/.cargo/bin:${PATH}"

# uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Python 3.12 as default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# Verify Rust works (sets default toolchain in settings.toml)
RUN rustup default stable && rustc --version && cargo --version

# ── Pre-compile Rust dependencies ─────────────────────────────────────────────
# Docker layer caching trick: copy only Cargo.toml + Cargo.lock + build.rs
# and create dummy src/lib.rs, then build deps into a shared target dir at a
# fixed path (/_temper-target).  CI must set CARGO_TARGET_DIR=/_temper-target
# to reuse these pre-compiled artifacts.
#
# This layer only invalidates when lock files change.  On CI runs,
# maturin develop / cargo check find pre-built deps and only recompile
# the local crate — saving 2-3 minutes per crate.

# Leaf crates (no internal path deps) — needed as deps by the main crates
COPY packages/temper-rust-router-core/Cargo.toml packages/temper-rust-router-core/Cargo.lock* packages/temper-rust-router-core/
COPY packages/temper-pcl-ir/Cargo.toml packages/temper-pcl-ir/Cargo.lock* packages/temper-pcl-ir/

# Main crates built in CI (maturin develop / cargo check)
COPY packages/temper-rust-router/Cargo.toml packages/temper-rust-router/Cargo.lock* packages/temper-rust-router/build.rs packages/temper-rust-router/
COPY packages/temper-drc-rs/Cargo.toml packages/temper-drc-rs/Cargo.lock* packages/temper-drc-rs/build.rs packages/temper-drc-rs/
COPY packages/temper-constraint-compiler/Cargo.toml packages/temper-constraint-compiler/Cargo.lock* packages/temper-constraint-compiler/build.rs packages/temper-constraint-compiler/
COPY packages/temper-design-bundle/Cargo.toml packages/temper-design-bundle/Cargo.lock* packages/temper-design-bundle/
COPY packages/temper-placer/temper-constraints/Cargo.toml packages/temper-placer/temper-constraints/Cargo.lock* packages/temper-placer/temper-constraints/build.rs packages/temper-placer/temper-constraints/

# Create dummy src/lib.rs stubs:
#   - rlib-only crates: trivial pub fn (no pyo3)
#   - cdylib/pyo3 crates: minimal #[pymodule] stub so the linker can
#     produce a dummy .so
RUN mkdir -p packages/temper-rust-router-core/src \
    && echo 'pub fn __temper_dummy() {}' > packages/temper-rust-router-core/src/lib.rs \
    && mkdir -p packages/temper-pcl-ir/src \
    && echo 'pub fn __temper_dummy() {}' > packages/temper-pcl-ir/src/lib.rs \
    && mkdir -p packages/temper-rust-router/src \
    && printf 'use pyo3::prelude::*;\n#[pymodule]\nfn temper_rust_router(_py: Python, _m: &Bound<PyModule>) -> PyResult<()> { Ok(()) }\n' > packages/temper-rust-router/src/lib.rs \
    && mkdir -p packages/temper-drc-rs/src \
    && printf 'use pyo3::prelude::*;\n#[pymodule]\nfn temper_drc_rs(_py: Python, _m: &Bound<PyModule>) -> PyResult<()> { Ok(()) }\n' > packages/temper-drc-rs/src/lib.rs \
    && mkdir -p packages/temper-constraint-compiler/src \
    && printf 'use pyo3::prelude::*;\n#[pymodule]\nfn temper_constraint_compiler(_py: Python, _m: &Bound<PyModule>) -> PyResult<()> { Ok(()) }\n' > packages/temper-constraint-compiler/src/lib.rs \
    && mkdir -p packages/temper-design-bundle/src \
    && printf '#[cfg(feature = "python")]\nuse pyo3::prelude::*;\n#[cfg(feature = "python")]\n#[pymodule]\nfn temper_design_bundle_python(_py: Python, _m: &Bound<PyModule>) -> PyResult<()> { Ok(()) }\npub fn __temper_dummy() {}\n' > packages/temper-design-bundle/src/lib.rs \
    && mkdir -p packages/temper-placer/temper-constraints/src \
    && printf 'use pyo3::prelude::*;\n#[pymodule]\nfn temper_constraints(_py: Python, _m: &Bound<PyModule>) -> PyResult<()> { Ok(()) }\n' > packages/temper-placer/temper-constraints/src/lib.rs

# Shared target dir at a fixed path so CI can reference it regardless of
# where actions/checkout mounts the workspace volume.
ENV CARGO_TARGET_DIR=/_temper-target

# Pre-compile all deps into the shared target dir.
#   - maturin crates: cargo build --release  (produces .rmeta + .rlib + .so)
#   - cargo check crate: cargo check           (produces .rmeta only)
# Overlapping deps (pyo3, serde, etc.) are compiled once and reused.
RUN cargo build --release --manifest-path packages/temper-drc-rs/Cargo.toml \
    && cargo build --release --manifest-path packages/temper-constraint-compiler/Cargo.toml \
    && cargo check --manifest-path packages/temper-constraint-compiler/Cargo.toml \
    && cargo build --release --manifest-path packages/temper-rust-router/Cargo.toml \
    && cargo build --release --manifest-path packages/temper-design-bundle/Cargo.toml --features python \
    && cargo build --release --manifest-path packages/temper-placer/temper-constraints/Cargo.toml

# Remove dummy lib.rs files so they don't conflict with the real source
# when the workspace is checked out in CI
RUN rm -f packages/temper-rust-router-core/src/lib.rs \
    packages/temper-pcl-ir/src/lib.rs \
    packages/temper-rust-router/src/lib.rs \
    packages/temper-drc-rs/src/lib.rs \
    packages/temper-constraint-compiler/src/lib.rs \
    packages/temper-design-bundle/src/lib.rs \
    packages/temper-placer/temper-constraints/src/lib.rs

WORKDIR /workspace
