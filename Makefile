# Temper: zapote validation workspace and ESP32 firmware.
# Board checks live in zapote/ (make -C zapote help).

.PHONY: help zapote firmware-test bridge-python

help:
	@echo "Temper targets:"
	@echo "  make -C zapote help  - Zapote ERC, DRC, DFM, layout and current checks (zapote/CHECKS.md)"
	@echo "  make zapote          - zapote Rust suite (cargo test --release --locked)"
	@echo "  make firmware-test   - firmware host tests (cmake + ctest)"
	@echo "  make bridge-python   - build zapote_bridge (the module zapote's unit tools import) into the uv venv"

zapote:
	cargo test --release --locked --manifest-path zapote/Cargo.toml --workspace

firmware-test:
	cmake -S firmware/test -B firmware/test/build
	cmake --build firmware/test/build -j
	cd firmware/test/build && ctest --output-on-failure

bridge-python:
	uv sync  # builds zapote/packages/zapote-bridge (maturin backend, python feature)
