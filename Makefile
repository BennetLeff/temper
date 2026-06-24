# Temper PCB Build Automation

ELEC_DIR = elec
ATO_ENTRY = src/main.ato:Top
BUILD_DIR = $(ELEC_DIR)/build

BOM_FILE = $(ELEC_DIR)/build/default.csv
BOM_PREV = $(ELEC_DIR)/build/default.csv.prev

.PHONY: all build netlist clean drc route gerbers help diff visualize regression perf-regression

# Show help for workflow commands
help:
	@echo "Temper PCB Build System"
	@echo "Targets:"
	@echo "  make build    - Run the full build pipeline"
	@echo "  make netlist  - Generate netlist from Atopile source"
	@echo "  make diff     - Show logical differences from last build"
	@echo "  make visualize- Show graphical schematic view"
	@echo "  make route    - Run the autorouter"
	@echo "  make drc      - Run KiCad DRC validation"
	@echo "  make clean    - Remove build artifacts"
	@echo ""

build: netlist footprints route drc

netlist:
	@echo "Building Atopile project..."
	@if [ -f $(BOM_FILE) ]; then cp $(BOM_FILE) $(BOM_PREV); fi
	cd $(ELEC_DIR) && uv tool run --from atopile ato build $(ATO_ENTRY)

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
	cd $(ELEC_DIR) && uv tool run --from atopile ato view $(ATO_ENTRY)

PCB_FILE = pcb/temper.kicad_pcb
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

regression:
	@echo "Running optimization quality regression suite..."
	uv run python3 scripts/check_regression.py

perf-regression:
	@echo "Running optimization performance regression suite..."
	uv run python3 scripts/check_perf_regression.py
