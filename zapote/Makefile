.PHONY: setup build check check-boards board-check qualify-buck engineering

HARNESS_DIR := ../harness-lab
CARGO ?= cargo
# Register each maintained Zapote unit here. Missing files fail closed.
UNIT_BOARDS := rtd/unit/candidate/section.kicad_pcb current-sense/candidate/section.kicad_pcb voltage-sense/candidate/section.kicad_pcb

setup:
	$(CARGO) metadata --locked --offline --no-deps --format-version 1 > /dev/null
	@echo "Zapote Rust workspace ready. Native editing also requires KiCad and the existing Python adapters."

build:
	$(CARGO) build --locked --workspace --bins --examples

check:
	$(CARGO) test --locked --workspace
	$(MAKE) check-boards

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
