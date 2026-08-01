# Temper PCB Build Automation

ELEC_DIR = elec
ATO_ENTRY = src/main.ato:Top
BUILD_DIR = $(ELEC_DIR)/build

BOM_FILE = $(ELEC_DIR)/build/default.csv
BOM_PREV = $(ELEC_DIR)/build/default.csv.prev

.PHONY: all build netlist clean drc route gerbers help diff visualize test test-fast onboard clean-onboard onboard-status extensions extensions-check venv-isolate worktree

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
	@echo "  make extensions      - Rebuild every pyo3/maturin Rust extension crate (fixes stale .so files)"
	@echo "  make extensions-check- Report stale/missing pyo3 extension crates without rebuilding"
	@echo "  make venv-isolate    - Give THIS worktree its own .venv, independent of any shared checkout"
	@echo "  make clean    - Remove build artifacts"
	@echo "  make onboard  - Guided quick-start achievement run"
	@echo "  make clean-onboard- Reset onboard checkpoints"
	@echo "  make onboard-status- Show cached onboard summary"
	@echo ""

build: netlist footprints schematics route drc

NETLIST_FILE = $(ELEC_DIR)/build/default.net

# The stamp is chained with `&&`, never as a separate recipe line: a stamp
# written next to a failed build would assert freshness for a broken netlist.
# check_domain_partition.py reads it and compares content instead of mtimes,
# which is what lets a restored netlist cache be trusted -- see
# scripts/_lib/freshness.py.
netlist:
	@echo "Building Atopile project..."
	@if [ -f $(BOM_FILE) ]; then cp $(BOM_FILE) $(BOM_PREV); fi
	cd $(ELEC_DIR) && uv tool run --from 'atopile>=0.2,<0.3' ato --non-interactive build $(ATO_ENTRY) \
	  && cd .. && uv run --no-sync python scripts/write_build_stamp.py \
	       --artifact $(NETLIST_FILE) --source-root $(ELEC_DIR)/src --glob '*.ato'

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
# Pass `--dist loadgroup` whenever passing `-n`. tests/conftest.py tags the
# pytest-dependency clusters with xdist_group so their providers stay on one
# worker. That is currently defensive rather than load-bearing -- as of
# 2026-07-28 pytest-dependency is not installed, so the marks are inert -- but
# once it is installed, any other --dist mode turns those dependents into
# SKIPS rather than failures, i.e. a green run that executed less. See the
# comment block in packages/temper-placer/tests/conftest.py.
#
# Measured on the CI group-1 file list (2026-07-28): serial 356s vs
# `-n 4 --dist loadgroup` 207s, identical per-test outcomes across 728 tests.
test:
	uv run --no-sync python -m pytest

test-fast:
	@echo "Running tests (excluding 'slow' markers, parallel -- use 'make test' for the serial reference run)..."
	uv run --no-sync python -m pytest -m "not slow" -n auto --dist loadgroup

# Rebuild every pyo3/maturin Rust extension crate in the repo (fixes the
# "stale .so" trap: a merge touches Rust source, the installed extension
# still imports but is silently frozen at its last successful build --
# scripts/check_stale_extensions.py detects this, this target fixes it).
#
# The crate list is NOT hardcoded here. `scripts/check_stale_extensions.py
# --list-crates` is the same discover_crates() source of truth the gate
# itself checks freshness against (a static scan of packages/ for
# pyproject.toml+Cargo.toml pairs with a maturin backend, a cdylib
# crate-type, and a pyo3 dependency) -- so this target can never drift
# from "how many pyo3 crates does this repo actually have" the way a
# hand-maintained list would. See extensions-crate-list-check below for
# the fallback-hardcoding contingency this repo doesn't currently need.
#
# `uv run --no-sync` (not plain `uv run`) on every step: a bare `uv run`
# re-resolves and can re-sync `.venv` against uv.lock, which -- for the
# three crates below that `uv sync --all-packages` does not build itself
# (temper-constraints is nested a level too deep for the
# `packages/*` workspace-members glob; see pyproject.toml
# [tool.uv.workspace]) -- would silently evict the very .so this target
# just built. That happened once already recovering from this exact
# staleness trap by hand.
#
# temper-constraints additionally needs PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
# (see .github/workflows/python-tests.yml's "Build and install
# temper-constraints" step) -- without it, its abi3 build fails against a
# newer CPython than the abi3-forward-compat table in the pinned pyo3
# version already knows about.
extensions:
	@echo "Rebuilding pyo3/maturin extension crates (crate list from 'scripts/check_stale_extensions.py --list-crates')..."
	@uv run --no-sync python3 scripts/check_stale_extensions.py --list-crates | while read -r crate_name manifest_path; do \
		echo "--- $$crate_name ($$manifest_path) ---"; \
		if [ "$$crate_name" = "temper-constraints" ]; then \
			PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 uv run --no-sync maturin develop --release --manifest-path "$$manifest_path" || exit 1; \
		else \
			uv run --no-sync maturin develop --release --manifest-path "$$manifest_path" || exit 1; \
		fi; \
	done
	@echo "Done. Run 'make extensions-check' to verify every crate is now fresh."

# Report-only: same gate CI runs, without rebuilding anything. Pair with
# `make extensions` as "check, then fix".
extensions-check:
	uv run --no-sync python3 scripts/check_stale_extensions.py

# Give THIS worktree its own, independent `.venv` instead of pointing
# UV_PROJECT_ENVIRONMENT at a shared checkout's -- see
# docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md
# and docs/evidence/2026-07-28-worktree-env-isolation.md for the incidents
# this closes: a concurrent session's `uv sync`/bare `uv run` silently
# reverting an extension THIS worktree just built (a shared-.venv failure
# mode content hashing does not touch, because the artifact really is
# replaced, just by someone else's build) -- and for the measured cost of
# doing this (~700 MB disk, ~85s wall time with a warm uv/cargo cache,
# because `.cargo/config.toml`'s shared `target-shared` build cache means
# the Rust half compiles incrementally even into a brand-new venv).
#
# This is deliberately NOT the default for every worktree unconditionally
# -- at fleet scale (dozens of agent worktrees, low double-digit GB free)
# giving every one its own copy regardless of whether it is doing active
# build/test work is the disk-multiplication problem this repo has already
# hit twice. Run this once, in a worktree that will build or test Rust
# extensions, at the start of that work.
#
# The stale-extension GATE itself (`make extensions-check`) does not
# depend on this choice either way: content-hash freshness
# (scripts/_lib/freshness.py) makes a shared `.venv` safe against the
# git-checkout-mtime false positive regardless of isolation, so isolating
# is about removing concurrent-mutation risk, not about the gate's own
# correctness.
venv-isolate:
	@echo "Provisioning this worktree's own .venv (uv sync --all-packages)..."
	uv sync --all-packages
	@echo "Building pyo3 extensions into it..."
	$(MAKE) extensions
	@echo "Done -- this worktree's .venv is now independent of any other checkout's."
	@echo "Run 'make extensions-check' any time to verify freshness."

# Create a dedicated, isolated worktree for one workstream. This is the
# default way to start new work in this repo: one worktree per branch/PR,
# branched from the right base, and -- with VENV=1 -- with its own `.venv`.
#
# Why: doing work in the shared main checkout mixes your uncommitted changes
# with other agents' in-flight work, so your changes must later be surgically
# extracted as a patch (the failure mode this target exists to remove). A
# dedicated worktree keeps one coherent unit of work in one place, verified
# and PR'd directly from there.
#
# Usage:
#   make worktree NAME=fix-driver-latch [BASE=origin/main] [VENV=1] [PATH=...]
#
#   NAME   branch (and PR) name for the workstream
#   BASE   ref to branch from (default origin/main); use the migration branch
#          when the work depends on unmerged work there
#   VENV   1 = also provision the worktree's own .venv (make venv-isolate,
#          ~85s warm-cache); add it when the workstream will build/test Rust
#          extensions, skip it for pure-Python/docs work to save ~700 MB disk
#   PATH   worktree path (default ../temper-wt-<NAME>, sibling of the repo)
#
# See docs/solutions/best-practices/per-workstream-worktree-2026-07-31.md
worktree:
	@test -n "$(NAME)" || { echo "usage: make worktree NAME=<branch> [BASE=origin/main] [VENV=1] [PATH=...]"; exit 1; }
	$(eval BASE ?= origin/main)
	$(eval WT_PATH ?= ../temper-wt-$(subst /,-,$(NAME)))
	@test ! -e "$(WT_PATH)" || { echo "error: $(WT_PATH) already exists"; exit 1; }
	git fetch origin
	git worktree add -b $(NAME) "$(WT_PATH)" $(BASE)
	@echo "worktree created: $(WT_PATH) on branch $(NAME) from $(BASE)"
	@echo "  cd $(WT_PATH)"
	@if [ "$(VENV)" = "1" ]; then echo "provisioning isolated .venv..."; $(MAKE) -C "$(WT_PATH)" venv-isolate; fi

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
