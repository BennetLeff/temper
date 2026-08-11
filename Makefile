# Temper PCB Build Automation

ELEC_DIR = elec
ATO_ENTRY = src/main.ato:Top
BUILD_DIR = $(ELEC_DIR)/build

BOM_FILE = $(ELEC_DIR)/build/default.csv
BOM_PREV = $(ELEC_DIR)/build/default.csv.prev

.PHONY: all build netlist clean drc route gerbers help diff visualize test test-fast onboard clean-onboard onboard-status extensions extensions-check venv-isolate worktree regen regen-check wasm-runner wasm-worker-stage wasm-worker-deploy

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

# NOTE: this does NOT place the board. `route` routes traces over whatever
# placement is already on disk, and `footprints` is a stub. Placement is a
# separate, deliberately human-gated CP-SAT solve with candidate selection --
# every recent pcb/temper.kicad_pcb change came from one, never from `make
# build`. CP-SAT placement is only deterministic when it terminates without
# hitting its timeout, which is why it is not automated here. See
# docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md.
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

# Re-pointed 2026-08-04 at the production board, which now exists -- this is the
# "re-point PCB_FILE at the production board once it exists" the previous comment
# here asked for. It had pointed at the quarantined 33-net benchmark fixture, so
# `make route` (and therefore `make build`) routed a fixture and `make drc`
# measured that fixture's output rather than the board.
PCB_FILE = pcb/temper.kicad_pcb
ROUTED_PCB = pcb/temper_routed.kicad_pcb

# Was `scripts/internal_route.py`, which had been unable to even import since
# 2026-07-10: it read `temper_placer.io.trace_writer` (deleted in 6d9e24db7 as
# dead code) and `jax` (declared in no pyproject.toml and absent from uv.lock).
# `docs/evidence/2026-07-30-rotation-sign-remaining-sites.md` recorded the script
# as dead on 2026-07-30; the Makefile kept calling it regardless, so this target
# was broken, not slow or wrong, for roughly four weeks. That script has since
# been RETIREd and deleted (2026-08-04) -- do not go looking for it.
#
# scripts/route_board.py is the live path -- it calls
# temper_placer.router_v6.adapter.route_pcb, the same entry point that produced
# the committed route in 556ccf4f and that
# test_production_board_routing_drc_regression exercises as a CI gate. Its own
# docstring already described itself as "the working entry point that `make
# route` and `scripts/internal_route.py` are not"; only this wiring was missing.
#
# --cell-size is not carried over: route_pcb owns its own grid parameters, and
# the committed route and the CI gate both use its defaults. Passing 0.2 here
# would have made `make route` diverge from the path everything else measures.
route: netlist
	@echo "Routing $(PCB_FILE) through router_v6 (route_pcb)..."
	uv run python3 scripts/route_board.py --pcb $(PCB_FILE) --output $(ROUTED_PCB)

# --all-track-errors is load-bearing, for determinism as much as completeness.
# Without it KiCad reports only a SUBSET of the errors on each track, and which
# subset varies between runs on a byte-identical board: measured over 11 runs,
# clearance 334-343 and shorting_items 148-174. With it those counts are stable
# and clearance reads 499 -- the same figure docs/STRATEGY.md records for this
# board. The earlier numbers were a sample, not a measurement.
#
# Omitting it here meant `make drc` disagreed with CI, with
# power_pcb_dataset/drc_ceiling.json, and with itself between runs. See the
# rationale in packages/temper-placer/src/temper_placer/validation/_drc_api.py.
#
# The pre-flight check below is load-bearing, not decorative: kicad-cli
# resolves a project by finding <stem>.kicad_pro next to the board, and
# when it can't, it does NOT error -- it silently drops every violation
# sourced from the project's custom pcb/temper.kicad_dru rules
# (track_width, and creepage -- the IEC 60335-1 HV/LV isolation check) and
# from temper.kicad_pro's rule_severities overrides (missing_courtyard,
# annular_width). `scripts/route_board.py` (the `route` target above)
# propagates a resolvable project onto $(ROUTED_PCB) automatically, but
# `make drc` can also be run standalone against a stale/hand-placed
# $(ROUTED_PCB) that predates that fix, so this still fails loud rather
# than measuring a silent subset. See
# docs/evidence/2026-08-08-drc-project-context-audit.md.
drc:
	@echo "Running KiCad DRC..."
	@if [ ! -f "$(ROUTED_PCB:.kicad_pcb=.kicad_pro)" ]; then \
		echo "ERROR: $(ROUTED_PCB:.kicad_pcb=.kicad_pro) not found next to $(ROUTED_PCB)."; \
		echo "kicad-cli DRC without a resolvable project silently drops"; \
		echo "creepage/track_width/missing_courtyard/annular_width -- refusing"; \
		echo "to run blind. Re-run 'make route' (which now propagates the"; \
		echo "project automatically), or see"; \
		echo "docs/evidence/2026-08-08-drc-project-context-audit.md."; \
		exit 1; \
	fi
	kicad-cli pcb drc --all-track-errors --exit-code-violations $(ROUTED_PCB)

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

# WASM verification tier (Track D): build the wasm-test-runner artifacts and
# stage them beside the Worker source so `wrangler deploy` can bundle them via
# the direct `.wasm` imports in packages/temper-worker/src/index.js. Full flow
# in docs/evidence/2026-08-07-phase1-u7-deploy-runbook.md.
#
#   make wasm-runner         # build the full-corpus .wasm only
#   make wasm-worker-stage   # build ALL EIGHT .wasm into packages/temper-worker/src/
#   make wasm-worker-deploy  # stage, then `wrangler deploy` all 8 Workers
#                            # (HUMAN step: requires a Cloudflare account +
#                            # login/token with Workers Scripts:Edit)
#
# CI equivalent, and the preferred path: the `workflow_dispatch`-only workflow
# .github/workflows/wasm-tier-deploy.yml runs exactly these steps and then
# VERIFIES the deployed corpus with tools/wasm/check_deployed_freshness.mjs.
#
# THREE BUGS FIXED HERE 2026-08-10 (Phase 5 U1, R5.2). All three made this
# "one-command deploy" a trap rather than a path, and all three fed the
# 2026-08-07..2026-08-10 staleness window this unit exists to close:
#
#  1. `wasm-runner` passed `--no-default-features` with no `--features`, which
#     turns OFF `wasm-test-registry` -- the only thing enabling
#     `temper-drc-rs/wasm-registry`, which gates `temper_drc_rs::
#     wasm_test_registry` (temper-drc-rs/src/lib.rs:47). The target has not
#     compiled at all since the family features landed; it fails with E0432
#     `unresolved import`. Verified 2026-08-10 by running it. That is the same
#     flag bug wasm-tier-nightly.yml's build step already carries a comment
#     about; the Makefile copy of it was never fixed.
#  2. `wasm-worker-stage` staged ONE module. `packages/temper-worker/src/
#     index.js` imports all eight, so a deploy from that state cannot bundle.
#     Worse, the seven per-family Workers -- the ones the tier actually
#     dispatches -- were not built or deployed by this path at all, which is
#     exactly how shards go stale while the full corpus looks current.
#  3. `stat -f %z` is macOS syntax; on Linux `-f` selects filesystem info and
#     prints garbage. Dropped in favour of `ls -lh` from the staging script.
#
# The staged copies are gitignored — never commit a built .wasm binary. Deploy
# is deliberately not reachable from `make build`; it is a credentialed,
# human-gated action, and nothing on the PR path can reach it.
#
# CARGO_TARGET_DIR (exported below) is the shared target dir, so this builds
# incrementally against whatever the rest of the repo already compiled.
WASM_RUNNER_MANIFEST = packages/temper-wasm-test-runner/Cargo.toml
WASM_RUNNER_ARTIFACT = $(CARGO_TARGET_DIR)/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm
WORKER_STAGED_WASM = packages/temper-worker/src/temper_wasm_test_runner.wasm
WASM_FAMILIES = drc emc erc safety placement routing infra

wasm-runner:
	@echo "Building temper-wasm-test-runner (wasm32-unknown-unknown)..."
	cargo build --release --target wasm32-unknown-unknown --no-default-features \
		--features wasm-test-registry \
		--manifest-path $(WASM_RUNNER_MANIFEST)

# temper-geometry on the same tier. A separate target rather than a flag on
# `wasm-runner` because the two produce different modules and different result
# sets: the expected-failure manifests are per-crate (run_wasm_tests.mjs exits
# non-zero on a manifest entry naming no registered test, so a geometry-only
# module cannot be judged against temper-drc-rs's manifest).
#
#   make wasm-geometry-test   # build + run all of temper-geometry's tests
#                             # under Node, on wasm32-unknown-unknown
wasm-geometry-test:
	@echo "Building temper-wasm-test-runner with temper-geometry's registry..."
	cargo build --release --target wasm32-unknown-unknown --no-default-features \
		--features geometry-wasm-test-registry \
		--manifest-path $(WASM_RUNNER_MANIFEST)
	node tools/wasm/run_wasm_tests.mjs $(WASM_RUNNER_ARTIFACT) \
		--expected-failures tools/wasm/wasm_expected_failures_geometry.json

# temper-thermal on the same tier, for the same reasons `wasm-geometry-test` is
# its own target: a different module, a different result set, and a per-crate
# expected-failure manifest that cannot judge a module built from another
# crate's registry.
#
#   make wasm-thermal-test    # build + run all of temper-thermal's registered
#                             # tests under Node, on wasm32-unknown-unknown
wasm-thermal-test:
	@echo "Building temper-wasm-test-runner with temper-thermal's registry..."
	cargo build --release --target wasm32-unknown-unknown --no-default-features \
		--features thermal-wasm-test-registry \
		--manifest-path $(WASM_RUNNER_MANIFEST)
	node tools/wasm/run_wasm_tests.mjs $(WASM_RUNNER_ARTIFACT) \
		--expected-failures tools/wasm/wasm_expected_failures_thermal.json

# Delegates to the committed staging script rather than duplicating its build
# matrix: one definition of "what the eight modules are", shared by this
# target, the deploy workflow, and the runbook.
wasm-worker-stage:
	bash scripts/stage_wasm_families.sh
	@echo "Local smoke test:  node tools/wasm/worker_local_server.mjs"

wasm-worker-deploy: wasm-worker-stage
	@echo "Deploying 8 Workers to Cloudflare (requires account + login/token)..."
	@for f in $(WASM_FAMILIES); do \
		echo "=== deploy temper-wasm-$$f ==="; \
		(cd packages/temper-worker/families/$$f && npx --yes wrangler@4 deploy) || exit 1; \
	done
	@echo "=== deploy temper-wasm-tier (full corpus) ==="
	cd packages/temper-worker && npx --yes wrangler@4 deploy
	@echo "Verifying the deployed corpus matches what was just built..."
	node tools/wasm/run_wasm_tests.mjs $(WORKER_STAGED_WASM) --json /tmp/staged_census.json
	node tools/wasm/check_deployed_freshness.mjs --built-json /tmp/staged_census.json

# Regenerate every derived artifact, refusing where regeneration would hide a
# defect (a hash-order NEW_SITE, or a drifted oracle pin). Run before pushing:
# a derived artifact drifting behind a merge turned main red four times on
# 2026-08-06, each time caught by a gate only AFTER the merge landed.
regen:
	uv run --no-sync python3 scripts/regen_derived.py

# Report-only: what CI's gates will see. Changes nothing.
regen-check:
	uv run --no-sync python3 scripts/regen_derived.py --check

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
# Shared cargo build cache. `.cargo/config.toml`'s relative `target-dir` gives
# every worktree a PRIVATE cache (measured 2026-08-05: five worktrees holding
# 10G/1.4G/750M/398M/109M separately), which is what drove .claude/worktrees to
# 51 GB. `--git-common-dir` points at the MAIN checkout's .git from any
# worktree, so this resolves to one absolute path everywhere -- including
# worktrees outside the repo tree, which no relative path can reach.
# CARGO_TARGET_DIR overrides build.target-dir.
CARGO_TARGET_DIR := $(shell dirname "$(shell git rev-parse --path-format=absolute --git-common-dir)")/target-shared
export CARGO_TARGET_DIR

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
#   - run-corpus reaches corpus_runner._run_board, which returns the
#     retired-optimizer error for every valid board (the JAX optimizer and
#     its stubs were removed in the cleanup C2 sweep), so every board failed
#     regardless of input.
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
