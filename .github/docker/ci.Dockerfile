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
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

# uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Python 3.12 as default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# Ensure HOME is consistent for GitHub Actions container jobs
ENV HOME=/root

WORKDIR /workspace
