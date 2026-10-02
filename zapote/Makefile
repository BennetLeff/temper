.PHONY: setup build check check-boards board-check check-thermal-oracle

CARGO ?= cargo
KICAD_CLI ?= kicad-cli
KICAD_PYTHON ?= python3
# Paths here are relative to zapote/ (or absolute). Override for a maintained variant.
UNIT_MANIFEST ?= validation/units.json
RUN_DIR ?= validation/runs/$(shell date -u +%Y%m%dT%H%M%SZ)
LAYOUT_BOARD ?= power-stage-120v/native-17/section.kicad_pcb
LAYOUT_RUN_DIR ?= validation/runs/layout-$(shell date -u +%Y%m%dT%H%M%SZ)
# Register each maintained Zapote unit here. Missing files fail closed.
UNIT_BOARDS := rtd/unit/candidate/section.kicad_pcb current-sense/candidate/section.kicad_pcb thermal-sense/candidate/section.kicad_pcb interlock/candidate/section.kicad_pcb gate-drive/candidate/section.kicad_pcb

setup:
	$(CARGO) metadata --locked --offline --no-deps --format-version 1 > /dev/null
	@echo "Zapote Rust workspace ready. Native editing also requires KiCad and the existing Python adapters."

build:
	$(CARGO) build --locked --workspace --bins --examples

check:
	$(CARGO) test --release --locked --workspace
	$(MAKE) check-layout
	$(MAKE) check-current
	$(MAKE) check-units

# Live geometry feedback after a placement/routing edit. This is measurement
# success, not electrical acceptance; report.json retains every model/input gap.
# LAYOUT_BASELINE optionally names a report made with the same evaluator.
.PHONY: check-layout
check-layout:
	@mkdir -p "$$(dirname "$(LAYOUT_RUN_DIR)")"
	$(CARGO) run --release --quiet --locked --bin zapote-layout-quality -- --native "$(LAYOUT_BOARD)" --python "$(KICAD_PYTHON)" --output "$(LAYOUT_RUN_DIR)" $(if $(LAYOUT_BASELINE),--baseline "$(LAYOUT_BASELINE)")

CURRENT_RUN_DIR ?= validation/runs/current-$(shell date -u +%Y%m%dT%H%M%SZ)
.PHONY: check-current
check-current:
	@mkdir -p "$$(dirname "$(CURRENT_RUN_DIR)")"
	$(CARGO) run --release --quiet --locked --bin zapote-layout-quality -- --native "$(LAYOUT_BOARD)" --python "$(KICAD_PYTHON)" --output "$(CURRENT_RUN_DIR)" --current-profile a4-two-terminal.v1 $(if $(CURRENT_BASELINE),--baseline "$(CURRENT_BASELINE)")

# Run the costly retained FEM replay in release; focused cargo tests stay debug.
# The runner's exit 2 means incomplete evidence. Make maps any recipe failure
# to its own nonzero status; inspect summary.json for fail vs indeterminate.
.PHONY: check-units check-native-oracle
check-units:
	@test -f "$(UNIT_MANIFEST)" || { echo 'UNIT_MANIFEST must name an existing unit manifest (relative to zapote/ or absolute).' >&2; exit 1; }
	@printf 'Unit manifest: %s (base: %s; release profile)\n' "$(UNIT_MANIFEST)" "$(CURDIR)"
	@mkdir -p "$$(dirname "$(RUN_DIR)")"
	$(CARGO) run --release --quiet --locked --bin zapote-unit-run -- "$(UNIT_MANIFEST)" "$(RUN_DIR)" "$(KICAD_CLI)" "$(KICAD_PYTHON)" --all

check-native-oracle:
	$(KICAD_PYTHON) validation/p2/test_extract.py

# Explicit live reference verification. Uses the bundled bar templates.
GMSH ?= gmsh
ELMERGRID ?= ElmerGrid
ELMERSOLVER ?= ElmerSolver
THERMAL_ORACLE_RUN_DIR ?= $(CURDIR)/validation/runs/thermal-oracle-$(shell date -u +%Y%m%dT%H%M%SZ)
.PHONY: check-thermal-oracle
check-thermal-oracle:
	@mkdir -p "$(dir $(THERMAL_ORACLE_RUN_DIR))"
	$(CARGO) run --locked -p zapote-thermal --bin zapote-thermal-reference -- "$(GMSH)" "$(ELMERGRID)" "$(ELMERSOLVER)" "$(THERMAL_ORACLE_RUN_DIR)"

check-boards:
	@set -e; for board in $(UNIT_BOARDS); do \
		$(CARGO) run --quiet --locked --bin zapote-board -- "$$board"; \
	done

board-check:
	@test -n "$(BOARD)" || { echo 'Usage: make -C zapote board-check BOARD=/absolute/path/to/board.kicad_pcb' >&2; exit 2; }
	$(CARGO) run --quiet --locked --bin zapote-board -- "$(BOARD)"

.PHONY: help
help:
	@printf '%s\n' \
	  'Zapote checks: see zapote/CHECKS.md for setup, scope, evidence and CI status.' \
	  'Run from the repository root: make -C zapote TARGET' \
	  '  check-layout          Native placement/routing measurements and comparisons' \
	  '  check-current         Layout plus conditional DC current, resistance and loss' \
	  '  check-units           ERC/DRC and engineering checks for five maintained units' \
	  '  board-check BOARD=... Physical stackup of one saved PCB (stackup only)' \
	  '  check-boards          Stackup checks for the maintained unit board list' \
	  '  check-native-oracle   Native manufacturing extraction tests' \
	  '  check-thermal-oracle  External Gmsh/Elmer reference check' \
	  '  check                 Release Rust tests, layout, current, then unit checks' \
	  'Native checks require KICAD_PYTHON; unit checks also require KICAD_CLI.' \
	  'Successful layout/current measurement is not full board acceptance.'
