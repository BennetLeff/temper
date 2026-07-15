# Temper PCB Build Automation

ELEC_DIR = elec
ATO_ENTRY = src/main.ato:Top
BUILD_DIR = $(ELEC_DIR)/build

BOM_FILE = $(ELEC_DIR)/build/default.csv
BOM_PREV = $(ELEC_DIR)/build/default.csv.prev

.PHONY: all build netlist clean drc route gerbers help diff visualize regression perf-regression onboard clean-onboard onboard-status

# Show help for workflow commands
help:
	@echo "Temper PCB Build System"
	@echo "Targets:"
	@echo "  make build    - Run the full build pipeline (netlist + schematics + route + drc)"
	@echo "  make netlist  - Generate netlist from Atopile source"
	@echo "  make schematics- Generate KiCad schematics from netlist"
	@echo "  make diff     - Show logical differences from last build"
	@echo "  make visualize- Show graphical schematic view"
	@echo "  make route    - Run the autorouter"
	@echo "  make drc      - Run KiCad DRC validation"
	@echo "  make clean    - Remove build artifacts"
	@echo "  make onboard  - Guided quick-start achievement run"
	@echo "  make clean-onboard- Reset onboard checkpoints"
	@echo "  make onboard-status- Show cached onboard summary"
	@echo ""

build: netlist footprints schematics route drc

netlist:
	@echo "Building Atopile project..."
	@if [ -f $(BOM_FILE) ]; then cp $(BOM_FILE) $(BOM_PREV); fi
	cd $(ELEC_DIR) && uv tool run --from 'atopile>=0.2,<0.3' ato --non-interactive build $(ATO_ENTRY)

schematics: netlist
	@echo "Generating schematics from Atopile netlist..."
	python3 scripts/gen_schematics.py

footprints:
	@echo "Generating footprints from code..."
	# This would call 'ato export footprints' or similar once FaC is fully integrated
	# For now, we use the generative modules defined in footprints.ato
	mkdir -p pcb/footprints.pretty
	@echo "Generative footprints ready: IGBT_TO247, SOIC16W_Isolated, LitzPad_15A"

diff:
	@if [ -f $(BOM_PREV) ]; then \
		./tools/ato_diff.py $(BOM_PREV) $(BOM_FILE); \
	else \
		echo "No previous build found to diff against."; \
	fi

visualize:
	cd $(ELEC_DIR) && uv tool run --from 'atopile>=0.2,<0.3' ato --non-interactive view $(ATO_ENTRY)

# Interim: points at the quarantined 33-component benchmark fixture until the
# real production board is generated from schematics. The identity gate (plan
# 2026-07-15-001 U4) will make routing fail-closed against a fixture-path board;
# re-point PCB_FILE at the production board once it exists.
PCB_FILE = pcb/benchmarks/temper_fixture_33.kicad_pcb
ROUTED_PCB = pcb/temper_routed.kicad_pcb

route: netlist
	@echo "Running internal maze router..."
	uv run python3 scripts/internal_route.py $(PCB_FILE) -o $(ROUTED_PCB) --cell-size 0.2

drc:
	@echo "Running KiCad DRC..."
	kicad-cli pcb drc --exit-code-violations $(ROUTED_PCB)

gerbers: build
	@echo "Exporting Gerbers..."
	# kicad-cli pcb export gerber ...

clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(BUILD_DIR)

REGRESSION_BOARD ?=

regression:
	@echo "Running optimization quality regression suite (corpus runner)..."
	@if [ -n "$(REGRESSION_BOARD)" ]; then \
		uv run python -m temper_placer.regression.cli run-corpus --board $(REGRESSION_BOARD) --json; \
	else \
		uv run python -m temper_placer.regression.cli run-corpus --json; \
	fi

perf-regression:
	@echo "Running optimization performance regression suite..."
	uv run python3 scripts/check_perf_regression.py

# Onboarding

.PHONY: onboard clean-onboard onboard-status

onboard:
	@bash scripts/onboard.sh

clean-onboard:
	@echo "Cleaning onboard checkpoints..."
	rm -rf .onboard

onboard-status:
	@bash scripts/onboard.sh --status
