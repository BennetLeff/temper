.PHONY: setup build check check-boards board-check qualify-buck engineering

HARNESS_DIR := ../harness-lab
CARGO ?= cargo
KICAD_CLI ?= kicad-cli
KICAD_PYTHON ?= python3
RUN_DIR ?= validation/runs/$(shell date -u +%Y%m%dT%H%M%SZ)
# Register each maintained Zapote unit here. Missing files fail closed.
UNIT_BOARDS := rtd/unit/candidate/section.kicad_pcb current-sense/candidate/section.kicad_pcb voltage-sense/candidate/section.kicad_pcb thermal-sense/candidate/section.kicad_pcb interlock/candidate/section.kicad_pcb gate-drive/candidate/section.kicad_pcb power-entry/candidate/section.kicad_pcb

setup:
	$(CARGO) metadata --locked --offline --no-deps --format-version 1 > /dev/null
	@echo "Zapote Rust workspace ready. Native editing also requires KiCad and the existing Python adapters."

build:
	$(CARGO) build --locked --workspace --bins --examples

check:
	$(CARGO) test --locked --workspace
	$(MAKE) check-units

# Exit 2 means incomplete engineering evidence, never a qualified pass.
.PHONY: check-units check-native-oracle
check-units:
	@mkdir -p "$(dir $(RUN_DIR))"
	$(CARGO) run --quiet --locked --bin zapote-unit-run -- validation/units.json "$(RUN_DIR)" "$(KICAD_CLI)" "$(KICAD_PYTHON)" --all

check-native-oracle:
	$(KICAD_PYTHON) validation/p2/test_extract.py

# Explicit live solver verification. Requires ngspice and a new output directory;
# the normal workspace tests also replay the pinned external measurements.
NGSPICE ?= ngspice
ORACLE_RUN_DIR ?= validation/runs/pfc-oracle-$(shell date -u +%Y%m%dT%H%M%SZ)
.PHONY: check-pfc-oracle
check-pfc-oracle:
	@mkdir -p "$(dir $(ORACLE_RUN_DIR))"
	$(CARGO) run --locked -p zapote-erc --example verify_pfc_spice -- "$(NGSPICE)" "$(ORACLE_RUN_DIR)"

check-boards:
	@set -e; for board in $(UNIT_BOARDS); do \
		$(CARGO) run --quiet --locked --bin zapote-board -- "$$board"; \
	done

board-check:
	@test -n "$(BOARD)" || { echo 'Usage: make -C zapote board-check BOARD=/absolute/path/to/board.kicad_pcb' >&2; exit 2; }
	$(CARGO) run --quiet --locked --bin zapote-board -- "$(BOARD)"

# Explicit legacy experiment entrypoints; never substituted for Zapote checks.
qualify-buck engineering:
	$(MAKE) -C $(HARNESS_DIR) $@
