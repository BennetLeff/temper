# Temper: zapote validation workspace, ESP32 firmware and the design-bundle crates.
# Board checks live in zapote/ (make -C zapote help).

.PHONY: help zapote firmware-test crates bridge-python

help:
	@echo "Temper targets:"
	@echo "  make -C zapote help  - Zapote ERC, DRC, DFM, layout and current checks (zapote/CHECKS.md)"
	@echo "  make zapote          - zapote Rust suite (cargo test --release --locked)"
	@echo "  make firmware-test   - firmware host tests (cmake + ctest)"
	@echo "  make crates          - test the design-bundle crate chain"
	@echo "  make bridge-python   - build zapote_bridge (the module zapote's unit tools import) into the uv venv"

zapote:
	cargo test --release --locked --manifest-path zapote/Cargo.toml --workspace

firmware-test:
	cmake -S firmware/test -B firmware/test/build
	cmake --build firmware/test/build -j
	cd firmware/test/build && ctest --output-on-failure

CRATES := temper-design-bundle temper-rust-router-core temper-py-bridge temper-py-bridge-derive temper-pcl-ir temper-geometry temper-io-types
crates:
	@set -e; for c in $(CRATES); do cargo test --locked --manifest-path packages/$$c/Cargo.toml; done

bridge-python:
	uv sync  # builds zapote/packages/zapote-bridge (maturin backend, python feature)
