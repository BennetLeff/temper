# Temper PCB Build Automation

ELEC_DIR = elec
ATO_ENTRY = src/main.ato:Top
BUILD_DIR = $(ELEC_DIR)/build

BOM_FILE = $(ELEC_DIR)/build/default.csv
BOM_PREV = $(ELEC_DIR)/build/default.csv.prev

.PHONY: all build netlist clean drc route gerbers help diff visualize test test-fast onboard clean-onboard onboard-status

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
	@echo "  make test     - Run the full test suite"
	@echo "  make test-fast- Run tests excluding 'slow' markers (inner loop)"
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

# Fast inner-loop test run: skips the 163 tests marked `slow` (of 6389).
#
# Deliberately a SEPARATE target rather than `-m "not slow"` in pyproject's
# addopts. CI invokes plain `uv run pytest <path>` and would inherit a global
# marker filter, silently shrinking what it checks -- and the slow set includes
# test_astar_3d_production_scale_spike, whose production-board failures were
# being actively investigated when this was added. A default that hides real
# failures is the gate-subset-blindness pattern documented in
# docs/solutions/best-practices/; opting IN to speed is safe, opting out of
# coverage by default is not.
#
# `make test` remains the full run. Use `make test-fast` while iterating.
#
# `test` stays single-process on purpose: it is the authoritative reference run,
# and a serial result is the baseline any parallel result gets checked against.
# `test-fast` is the inner loop, so it opts in to xdist.
#
# `--dist loadgroup` is NOT optional when passing `-n`. tests/conftest.py tags
# the pytest-dependency clusters with xdist_group; under any other --dist mode
# their providers scatter across workers and the dependents SKIP rather than
# fail -- a green run that executed less. Measured on the CI group-1 file list
# (2026-07-28): serial 356s vs `-n 4 --dist loadgroup` 207s, with byte-identical
# per-test outcomes (728 tests, zero pass->skip transitions).
test:
	uv run --no-sync python -m pytest

test-fast:
	@echo "Running tests (excluding 'slow' markers, parallel -- use 'make test' for the serial reference run)..."
	uv run --no-sync python -m pytest -m "not slow" -n auto --dist loadgroup

gerbers: build
	@echo "Exporting Gerbers..."
	# kicad-cli pcb export gerber ...

clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(BUILD_DIR)

# RETIRED 2026-07-27: `regression` and `perf-regression` both drove the
# JAX/benders_loop placement path, which no longer exists.
#   - run-corpus reaches corpus_runner.py:416-419, which raises
#     NotImplementedError("JAX optimizer removed."), so every board failed at
#     setup regardless of input.
#   - check_perf_regression.py imported `jax` and `temper_placer.losses.*`;
#     both are gone from the tree, so it died on ModuleNotFoundError before
#     doing any work. The script is deleted.
# Both were masked in CI as runner flakiness rather than a removed capability.
# Restoring quality/perf regression coverage needs a placement strategy that
# still exists; these targets could not provide it.

# Onboarding

.PHONY: onboard clean-onboard onboard-status

onboard:
	@bash scripts/onboard.sh

clean-onboard:
	@echo "Cleaning onboard checkpoints..."
	rm -rf .onboard

onboard-status:
	@bash scripts/onboard.sh --status
