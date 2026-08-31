# CI base image: pre-installed system dependencies for temper workflows
# Rebuilt when lock files change; versioned by uv.lock + Cargo.lock hash
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# System packages: Python 3.12, Rust build deps, ngspice
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git git-lfs \
    python3.12 python3.12-dev python3.12-venv \
    build-essential cmake pkg-config \
    libclang-dev \
    patchelf \
    ngspice \
    && rm -rf /var/lib/apt/lists/*

# KiCad (large package, separate layer for caching)
#
# PINNED 2026-08-04. `ppa:kicad/kicad-10.0-releases` is a rolling PPA: it serves
# only the newest 10.0.x and drops the previous one. Unpinned, `kicad-cli` -- the
# oracle every DRC baseline and every entry in power_pcb_dataset/drc_ceiling.json
# is measured against -- could change under the repo with no commit landing here.
#
# That is not hypothetical. It already happened: every provenance block in
# tests/placer/cp_sat/test_regression_drc.py records "kicad-cli 10.0.4, macOS
# arm64", while this image had silently rolled to 10.0.5. Measured on one commit
# (PR #673) across the two environments, byte-identical router output gave
# `total` 1395 on macOS/10.0.4 and 1502 in this container -- a +107 swing from
# the environment alone, with `unconnected_items` identical at 460 (connectivity
# is environment-independent; the geometric categories are not). See
# docs/evidence/2026-08-04-router-output-rebaseline-interim.md.
#
# CHANGING THIS VERSION IS A RE-BASELINE EVENT, not a routine bump. Every DRC
# constant in the repo is measured against it. When the PPA drops this version
# the image build fails loudly on a missing apt version -- that is the intended
# behaviour, and it is strictly better than the counts moving silently. To bump:
# raise the version here, then re-measure the baselines against the new binary
# and land both together, per AGENTS.md's same-PR re-measurement rule.
ARG KICAD_VERSION=10.0.6~ubuntu24.04.1
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends software-properties-common \
    && add-apt-repository -y ppa:kicad/kicad-10.0-releases \
    && apt-get update && apt-get install -y --no-install-recommends \
        "kicad=${KICAD_VERSION}" "kicad-footprints=${KICAD_VERSION}" \
    && kicad-cli version \
    && rm -rf /var/lib/apt/lists/*

# Rust toolchain (pinned, minimal profile). Toolchain bumps are deliberate so
# new Clippy lints cannot break an unchanged image definition.
ARG RUST_VERSION=1.97.0
ENV RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain "${RUST_VERSION}" --profile minimal \
    && /root/.cargo/bin/rustup component add clippy
ENV PATH="/root/.cargo/bin:${PATH}"

# uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Python 3.12 as default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# Verify Rust works (sets default toolchain in settings.toml)
RUN rustup default "${RUST_VERSION}" && rustc --version && cargo --version

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
COPY packages/temper-py-bridge-derive/Cargo.toml packages/temper-py-bridge-derive/Cargo.lock* packages/temper-py-bridge-derive/
COPY packages/temper-py-bridge/Cargo.toml packages/temper-py-bridge/Cargo.lock* packages/temper-py-bridge/
COPY packages/temper-geometry/Cargo.toml packages/temper-geometry/Cargo.lock* packages/temper-geometry/

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
    && mkdir -p packages/temper-py-bridge-derive/src \
    && echo '// Dummy proc-macro crate for dependency pre-compilation.' > packages/temper-py-bridge-derive/src/lib.rs \
    && mkdir -p packages/temper-py-bridge/src \
    && echo 'pub fn __temper_dummy() {}' > packages/temper-py-bridge/src/lib.rs \
    && mkdir -p packages/temper-geometry/src \
    && echo 'pub fn __temper_dummy() {}' > packages/temper-geometry/src/lib.rs \
    && mkdir -p packages/temper-rust-router/src \
    && printf 'use pyo3::prelude::*;\n#[pymodule]\nfn temper_rust_router(_py: Python, _m: &Bound<PyModule>) -> PyResult<()> { Ok(()) }\n' > packages/temper-rust-router/src/lib.rs \
    && mkdir -p packages/temper-drc-rs/src \
    && echo 'pub fn __temper_dummy() {}' > packages/temper-drc-rs/src/lib.rs \
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
    packages/temper-py-bridge-derive/src/lib.rs \
    packages/temper-py-bridge/src/lib.rs \
    packages/temper-geometry/src/lib.rs \
    packages/temper-rust-router/src/lib.rs \
    packages/temper-drc-rs/src/lib.rs \
    packages/temper-constraint-compiler/src/lib.rs \
    packages/temper-design-bundle/src/lib.rs \
    packages/temper-placer/temper-constraints/src/lib.rs

# ── Pre-install third-party Python dependencies ───────────────────────────────
# Same trick as the cargo layer above, for Python. `uv sync --all-packages` was
# measured at 87s per job on 2026-08-03 -- paid by every container job, even on
# a venv cache hit (the cache restores .venv but uv still resolves and links
# every package). With 79% of the workflow's job-time already going to setup,
# that was the single largest un-harvested win.
#
# Only THIRD-PARTY packages are baked. The 15 workspace members are deliberately
# excluded: they install editable, pointing at the CI checkout path, which does
# not exist at image-build time. CI's `uv sync --all-packages --inexact` still
# runs and installs those -- it just no longer has to install the ~70
# third-party packages (429 MB unpacked; scipy, ortools, pandas, numpy) first.
#
# requirements-ci.txt is generated from uv.lock and a hygiene gate asserts the
# two stay in sync, so this layer invalidates exactly when the lockfile changes:
#   uv export --all-packages --no-emit-workspace --format requirements-txt --no-hashes
COPY requirements-ci.txt /tmp/requirements-ci.txt
RUN uv venv /_temper-venv \
    && VIRTUAL_ENV=/_temper-venv uv pip install --no-cache -r /tmp/requirements-ci.txt \
    && rm -rf /root/.cache/uv

# Deliberately NO `ENV VIRTUAL_ENV` / `ENV UV_PROJECT_ENVIRONMENT` /
# `ENV PATH` for this venv. Nine workflows share this image, and six of them
# (regression, r9-evidence, placer-regression, cp-sat-benchmarks, pr-perf-check,
# pr-pipeline-scorecard) build their own workspace .venv and set VIRTUAL_ENV to
# it at job level. Setting UV_PROJECT_ENVIRONMENT here overrode nothing they
# declare -- a job-level VIRTUAL_ENV does not displace it -- so `uv pip install`
# targeted their .venv while `uv run` targeted /_temper-venv, and regression
# failed with `Failed to spawn: maturin` on 2026-08-03.
#
# The image offers the environment; consumers opt in. python-tests.yml sets both
# VIRTUAL_ENV and UV_PROJECT_ENVIRONMENT to /_temper-venv at job level.

WORKDIR /workspace
