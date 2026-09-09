.PHONY: build check qualify

export CARGO_TARGET_DIR := $(abspath $(shell git rev-parse --path-format=absolute --git-common-dir)/../target-shared)
export TEMPER_E00_JUDGE := $(CARGO_TARGET_DIR)/debug/temper-harness-e00
PYTHON ?= python3
OUTPUT ?= runs/qualification-$(shell date -u +%Y%m%dT%H%M%SZ)

build:
	cargo build --locked

check:
	cargo test --locked
	cargo clippy --all-targets --all-features --locked -- -D warnings
	cargo fmt -- --check
	ruff check --isolated --select E4,E7,E9,F,I *.py
	ruff format --isolated --check *.py
	$(PYTHON) -m compileall -q .

qualify: build
	$(PYTHON) qualify.py $(OUTPUT)
