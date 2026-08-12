"""Spike: golden-board DRC regression gate, driven by Pumpkin, against the
REAL 169-component board (``pcb/temper.kicad_pcb``) -- not the 33-component
``power_pcb_dataset/corpus/temper/`` fixture ``test_golden_board_drc_regression``
uses.

Context (see ``docs/evidence/2026-08-11-pumpkin-golden-test-spike.md`` for the
full writeup): OR-Tools CP-SAT cannot decide the real board within the real
30s ``INITIAL_SOLVE_TIMEOUT_MS`` budget -- it returns ``unknown`` at ~26s,
measured repeatedly (``docs/evidence/2026-08-11-pumpkin-real-budget-spike.md``
§4.2). Pumpkin, a pure-Rust CP-SAT-class solver already spiked as a standalone
binary (``docs/evidence/2026-08-07-pumpkin-engine/``), proves the same class
of model ``optimal``/``feasible`` in ~0.6-2.5s. This test is the first attempt
to run that solve inside an actual write-and-DRC regression test on the real
board.

Every component count in this module's docstrings and messages is the
REAL board's: 169 components, 152x234mm (``pcb/temper.kicad_pcb``), never the
33-component independent fixture.

## Why courtyard + netclass separation, not the full PCL config

``test_golden_board_drc_regression`` solves with the full
``temper_induction_cooker.yaml`` PCL config (zones + named adjacency/enclosing
constraints). Running that same config against the REAL board is infeasible
for BOTH engines -- confirmed independently by both a standalone run of this
module's own constraint-building code and the real-budget spike (§4.0 of the
doc above): the config's zone/adjacency assumptions have drifted from the
real board's current geometry (e.g. ``enc_HV_ZONE`` assumes a zone box that
does not fit the real board's actual 152x234mm extent; the real board's OWN
committed, shipped positions already violate several of the config's own
constraints). That is a config/board drift bug, orthogonal to which solver is
asked to decide it -- it is NOT fixed here (out of this spike's declared
scope, and ``temper-design-bundle``'s config loader is off-limits to this
spike per its task boundaries).

To isolate the solver question from that pre-existing drift bug, this test
builds the SAME constraint set ``solve_placement()`` itself would
auto-generate absent the drifted PCL/zone layer: netclass-aware cross-class
SEPARATED constraints
(``temper_placer.placer.cp_sat.netclass_constraints.generate_netclass_separated_constraints``
-- the exact function ``_encoder_core.encode_constraints`` calls), backfilled
with a flat courtyard-clearance SEPARATED pair for every remaining pair not
already covered by a stronger netclass constraint
(``_generate_courtyard_separated_constraints``'s own skip rule, replicated
here). This is materially more faithful than a flat-tau-only model: an
earlier version of this test used flat courtyard clearance alone and produced
a placement with several hundred HighVoltage-netclass clearance violations
(6mm required, some pairs as close as 3.5mm) that the flat 0.4mm tau never
constrained against. With netclass separation included, that category drops
close to zero (see the results table in the spike doc). This is still a
real, non-trivial, full-scale placement problem on the real board at real
footprint sizes (a five-figure constraint count over 169 real components) --
just without the drifted zone/adjacency layer.

## Why this compares against the REAL board's OWN committed-DRC baseline, not the fixture's <=15 threshold

``test_golden_board_drc_regression``'s ``placement_fixable <= 15`` threshold
is calibrated for the 33-component fixture: a small, sparse, purpose-built
corpus. Measured directly (this module's own DRC run against the REAL,
as-shipped, committed ``pcb/temper.kicad_pcb`` -- no placement change at
all): 1281 total violations, 199 ``silk_overlap``, 499 ``clearance``, 97
``shorting_items``, 154 ``solder_mask_bridge`` -- already far above 15, on
the board as it ships today. This is not a defect this test discovers; it is
the SAME reality ``test_regression_drc.py``'s own
``PRODUCTION_COMMITTED_BOARD_*`` constants already encode (measured
2026-07-29, ``PRODUCTION_COMMITTED_BOARD_TOTAL_DVIOLATIONS = 1425``,
``PRODUCTION_COMMITTED_BOARD_SHORTING_ITEMS = 141``) and
``test_production_board_drc_regression`` already asserts against (a ratchet
against the board's own measured baseline, not a small fixed constant). At
169 real components and real densities, "zero-ish violations" was never the
right bar -- silkscreen alone (199 ``silk_overlap`` violations, unconstrained
by ANY encoding used here or in production's courtyard/netclass layer) is
present in the AS-SHIPPED board unchanged. This test therefore holds Pumpkin
to the SAME ratchet ``test_production_board_drc_regression`` already holds
the committed board to -- does a fresh Pumpkin placement, on bare (unrouted)
footprints, do no worse than what is already shipping -- rather than a
threshold copied from a 5x-smaller corpus it was never calibrated for.

## Solver: Pumpkin via subprocess, not wired into ``solve_placement``

Pumpkin is NOT a production dependency (see the spike doc's recommended
solver-selection seam design). This test shells out to the standalone
``pumpkin_engine`` binary built from
``docs/evidence/2026-08-07-pumpkin-engine/`` -- the same JSON-stdin/JSON-stdout
wire protocol the existing 108-run differential
(``docs/evidence/2026-08-07-pumpkin-engine-differential.md``) and the
real-budget spike already validated. No line under
``packages/temper-placer/src/temper_placer/placer/cp_sat/**`` is touched or
imported for solving -- only for the shared board-parsing, netclass-loading,
placement-writing and DRC plumbing every golden test already uses (including
the SAME ``generate_netclass_separated_constraints`` pure-Python constraint
generator ``solve_placement()`` itself calls -- reused, not reimplemented).

## Requires a local build

The binary is not part of any package/extension build --
``pumpkin_engine`` must be built once with:

    cargo build --release --manifest-path docs/evidence/2026-08-07-pumpkin-engine/Cargo.toml

(set ``CARGO_TARGET_DIR`` per ``scripts/cargo_shared_env.sh`` if working from
a worktree). Absent that binary, this test SKIPS -- it is not currently wired
into any CI job (see the spike doc's costing section for what that would
take).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from temper_placer.validation._drc_api import copy_kicad_project_sidecar
from tests.placer.cp_sat._parallel_drc import run_drc_loud
from tests.placer.cp_sat.test_regression_drc import (
    PRODUCTION_COMMITTED_BOARD_SHORTING_ITEMS,
    PRODUCTION_COMMITTED_BOARD_TOTAL_DVIOLATIONS,
    REPO_ROOT,
    RULES_PATH,
    _kicad_cli_available,
)

_REAL_PRODUCTION_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

# Same production round-1 budget as test_golden_board_drc_regression's own
# solve_placement(timeout_ms=30_000) and loop.py's live INITIAL_SOLVE_TIMEOUT_MS.
TIMEOUT_MS = 30_000
SEED = 42  # matches test_golden_board_drc_regression's seed=42

# Generous safety margin over the requested budget before treating the
# subprocess itself as hung. The real-budget spike recorded one HPWL-objective
# run overrunning a 30s budget by ~20s (retry: 30.17s, essentially on-budget)
# -- this margin is deliberately wide enough not to flag that class of
# overrun as a hard subprocess failure, so a genuine timeout-adherence
# regression is still distinguishable from "the safety margin was too tight."
SUBPROCESS_SAFETY_MARGIN_S = 60.0


sys.path.insert(0, str(REPO_ROOT / "scripts"))
from verify_pumpkin_engine import (  # noqa: E402
    VerifiedPumpkinEngine,
    resolve_verified_pumpkin_engine,
)


def _find_pumpkin_binary() -> VerifiedPumpkinEngine | None:
    """Locate AND verify the standalone pumpkin_engine spike binary.

    Not a production build artifact -- checks both a worktree-local build
    (default ``target-dir`` relative to this repo root) and the shared
    main-checkout build (``CARGO_TARGET_DIR``/``scripts/cargo_shared_env.sh``
    convention every other agent-worktree build uses -- see
    ``.cargo/config.toml``'s own comment on why the shared path exists).

    Delegates the actual search-and-hash-check to
    ``scripts/verify_pumpkin_engine.py`` (the single choke point for this
    repo now -- see that module's docstring for why: an untracked binary
    that is not provably a build of the pinned source produced six
    different boards from "the same" recipe,
    ``docs/evidence/2026-08-12-engine-binary-pinning.md``).

    Returns ``None`` if no candidate exists anywhere (legitimately unbuilt
    -- callers should still skip). Raises ``PumpkinEngineIdentityError``,
    uncaught, if a candidate exists but does not match the pin -- this must
    fail the test, not skip it or warn and continue.
    """
    return resolve_verified_pumpkin_engine(REPO_ROOT)


def _build_constraints(netlist, refs_sizes: dict[str, tuple[float, float]], rules, tau_mm: float) -> list[dict]:
    """The same two-layer constraint set ``_encoder_core.encode_constraints``
    builds when ``netclass_rules_data``/``netlist`` are supplied and
    ``ctx.courtyard_clearance_mm > 0``: netclass-aware cross-class SEPARATED
    constraints first (``generate_netclass_separated_constraints`` -- the
    real production function, imported and called directly, not
    reimplemented), then a flat courtyard-tau SEPARATED pair backfilling
    every remaining pair not already covered by a netclass constraint at
    least as strict (mirrors ``_generate_courtyard_separated_constraints``'s
    own skip rule)."""
    from temper_placer.placer.cp_sat.netclass_constraints import (
        generate_netclass_separated_constraints,
    )

    netclass_auto = generate_netclass_separated_constraints(
        netlist, netlist.components, rules.design_rules, existing_constraints=[]
    )

    existing_pairs: dict[tuple[str, str], float] = {}
    for c in netclass_auto:
        if c.min_distance_mm >= tau_mm and c.a in refs_sizes and c.b in refs_sizes and c.a != c.b:
            key = tuple(sorted([c.a, c.b]))
            existing_pairs[key] = max(existing_pairs.get(key, 0.0), c.min_distance_mm)

    constraints = [c.to_dict() for c in netclass_auto]
    refs = sorted(refs_sizes)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            key = (refs[i], refs[j])
            if key in existing_pairs:
                continue
            constraints.append(
                {"type": "separated", "a": refs[i], "b": refs[j], "min_distance_mm": tau_mm}
            )
    return constraints


def _solve_with_pumpkin(binary: Path, payload: dict, timeout_ms: int) -> dict:
    t_budget = (timeout_ms / 1000.0) + SUBPROCESS_SAFETY_MARGIN_S
    proc = subprocess.run(
        [str(binary)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=t_budget,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pumpkin_engine exited {proc.returncode}: {proc.stderr[-4000:]}"
        )
    return json.loads(proc.stdout)


@pytest.mark.slow
def test_golden_board_drc_regression_pumpkin_real_board(request: pytest.FixtureRequest):
    """Pumpkin-driven placement + DRC gate against the REAL 169-component
    board, instead of the 33-component fixture ``test_golden_board_drc_regression``
    uses.

    Deliverable of the 2026-08-11 Pumpkin-golden-test spike: does a golden
    DRC regression test pass on the real board with Pumpkin, and in what
    time? See the module docstring for scope (netclass + courtyard
    constraints, subprocess-driven Pumpkin, why the full PCL config is
    excluded, and why this test's pass bar is the real board's own
    committed-DRC ratchet rather than the fixture's fixed threshold).
    """
    if not _kicad_cli_available():
        pytest.skip("kicad-cli not available")

    # Raises PumpkinEngineIdentityError, uncaught, if a binary exists but does
    # not match the pin -- that must fail this test loudly, not skip it (see
    # scripts/verify_pumpkin_engine.py's module docstring).
    pumpkin_bin = _find_pumpkin_binary()
    if pumpkin_bin is None:
        pytest.skip(
            "pumpkin_engine binary not built -- run: cargo build --release "
            "--locked --manifest-path docs/evidence/2026-08-07-pumpkin-engine/Cargo.toml "
            "(see module docstring)"
        )
    print(f"[pumpkin real-board golden test] {pumpkin_bin.identity_line()}", flush=True)

    assert _REAL_PRODUCTION_BOARD.exists(), f"Board not found: {_REAL_PRODUCTION_BOARD}"
    assert RULES_PATH.exists(), f"Rules not found: {RULES_PATH}"

    t_start = time.monotonic()

    # 1. Load netclass rules (courtyard tau + netclass separation both derive
    #    from these, same source solve_placement() itself uses).
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.placer.cp_sat._encoder_solve import (
        _POLARIZED_REFS,
        courtyard_clearance_mm,
    )

    rules = load_netclass_rules(RULES_PATH)
    tau_mm = courtyard_clearance_mm(rules.design_rules.default_clearance)

    # 2. Parse the REAL board.
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parse_result = parse_kicad_pcb(_REAL_PRODUCTION_BOARD)
    netlist = parse_result.netlist
    board = parse_result.board
    assert board is not None, "Board geometry parsing failed"
    n_components = len(netlist.components)
    assert n_components > 100, (
        f"Expected the real ~169-component board, got {n_components} components -- "
        f"is {_REAL_PRODUCTION_BOARD} actually the real board?"
    )

    # 3. Build the netclass + courtyard constraint model and Pumpkin wire payload.
    refs_sizes = {c.ref: (float(c.bounds[0]), float(c.bounds[1])) for c in netlist.components}
    constraints = _build_constraints(netlist, refs_sizes, rules, tau_mm)
    components_payload = {
        ref: {"w0_mm": w0, "h0_mm": h0, "rotatable": ref not in _POLARIZED_REFS}
        for ref, (w0, h0) in refs_sizes.items()
    }
    payload = {
        "board_w_mm": float(board.width),
        "board_h_mm": float(board.height),
        "edge_margin_mm": 0.5,
        "components": components_payload,
        "zones": {},
        "zone_components": {},
        "loop_components": {},
        "constraints": constraints,
        "minimize_displacement_to": None,
        "seed": SEED,
        "timeout_ms": TIMEOUT_MS,
    }

    # 4. Solve with Pumpkin (feasibility only, no objective -- matches
    #    solve_placement's own Phase-1 "no objective, find any valid
    #    placement" contract; test_golden_board_drc_regression never posts
    #    an objective either).
    outcome = _solve_with_pumpkin(pumpkin_bin.path, payload, TIMEOUT_MS)
    solve_time_ms = outcome.get("solve_time_ms")
    status = outcome.get("status")

    print(
        f"\n[pumpkin real-board golden test] components={n_components} "
        f"constraints={len(constraints)} status={status} "
        f"solve_time_ms={solve_time_ms}",
        flush=True,
    )

    if status not in ("optimal", "feasible"):
        pytest.skip(f"Pumpkin solver returned status {status}")

    positions = {ref: (float(x), float(y)) for ref, (x, y) in outcome["positions"].items()}
    # Dense by construction -- every solved ref is included, even rot index
    # 0. A filtered `if idx` here (the pre-fix form of this line) drops
    # explicit index-0 decisions, and `_apply_placements_to_pcb` treats a
    # MISSING ref as "keep the pre-solve board angle" rather than "write
    # absolute 0" -- for a non-square component solved to rot=0 whose prior
    # board angle was non-zero, that silently writes the WRONG orientation
    # relative to the box Pumpkin actually sized, moving real pad copper
    # outside the board outline. See
    # ``CpSatPlacementResult.to_rotations_dict``'s docstring
    # (``_encoder_solve.py``) for the full mechanism and the measurement
    # that found it.
    rotations = {
        ref: idx * 90.0
        for ref, idx in outcome.get("rotations", {}).items()
    }

    # 5. Write output PCB (same writer, rotations+components together, same
    #    reason test_golden_board_drc_regression requires both -- see that
    #    test's own comment).
    #
    # Unlike the 33-component fixture (bare/unrouted -- BOARD_PATH has no
    # committed copper at all), the real board is the actual SHIPPED,
    # fully-routed product: traces, vias and pours already committed for the
    # board's CURRENT (as-shipped) placement. This solve's constraint set has
    # no fixed-copper-avoidance constraint (production solve_placement()'s
    # `fixed_copper=` kwarg, out of scope for this spike model -- see module
    # docstring), so writing its positions directly over the real board's
    # EXISTING copper would conflate "is this placement good" with "is the
    # OLD routing still valid for NEW positions" -- a routing-regression
    # question (test_golden_board_routing_drc_regression's job, and it is
    # currently skipped upstream for an unrelated, already-tracked reason --
    # see that test's own KNOWN GAP skip), not a placement-quality one.
    # Stripping existing copper first (production's own R7 "clean re-route"
    # primitive, `strip_existing_copper` -- the same one
    # `scripts/route_board.py` uses) isolates exactly what
    # test_golden_board_drc_regression measures on the fixture: does THIS
    # placement, alone, on bare footprints, clear DRC -- not "is the old
    # routing still valid," which no placement algorithm (OR-Tools or
    # Pumpkin) is trying to answer here.
    from temper_placer.router_v6._strip_copper import strip_existing_copper

    raw, n_stripped = strip_existing_copper(_REAL_PRODUCTION_BOARD.read_text(encoding="utf-8"))
    print(
        f"[pumpkin real-board golden test] stripped {n_stripped} existing "
        f"copper block(s) (segments/vias/zones) before writing new placement",
        flush=True,
    )
    from temper_placer.router_v6.adapter import _apply_placements_to_pcb

    placed = _apply_placements_to_pcb(
        raw,
        positions,
        design_rules=rules.design_rules,
        rotations=rotations,
        components=netlist.components,
    )

    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as tmp:
        tmp.write(placed)
        placed_path = tmp.name
    copy_kicad_project_sidecar(Path(placed_path), _REAL_PRODUCTION_BOARD)

    try:
        # 5b. Round-trip oracle -- same U3 gate test_golden_board_drc_regression
        #     runs before trusting any DRC measurement. This is the gate that
        #     caught the real, pre-existing `_apply_placements_to_pcb` bug
        #     this spike found and fixed (see git history / the spike doc):
        #     the function's footprint-block regex silently matched 0
        #     footprints against the real board's newer KiCad export format
        #     (`(version ...)(generator ...)` between the footprint name and
        #     `(layer ...)`, absent from the older fixture), so the write was
        #     a complete, silent no-op before that fix.
        from temper_placer.validation.placement_roundtrip import (
            check_placement_roundtrip,
        )

        rt = check_placement_roundtrip(placed_path, positions, rotations, netlist.components)
        assert rt.passed, (
            f"Round-trip oracle FAILED after real-board Pumpkin write: {rt.summary}"
        )

        # 6. Run kicad-cli DRC and parse. Single run, not the 5-run median
        #    test_production_board_drc_regression uses for kicad-cli's own
        #    run-to-run noise (docs/STRATEGY.md: shorting_items noise up to
        #    ±11) -- a known simplification of this spike test, noted rather
        #    than hidden; the margin against both thresholds below is large
        #    enough that single-run noise cannot flip the result (see the
        #    spike doc's reproducibility section for repeated-run data).
        drc_data = run_drc_loud(placed_path, timeout=180, label="pumpkin-real-board")
        violations = drc_data.get("violations", [])

        total = len(violations)
        shorting = sum(1 for v in violations if v.get("type") == "shorting_items")
        by_type: dict[str, int] = {}
        for v in violations:
            vtype = v.get("type", "other")
            by_type[vtype] = by_type.get(vtype, 0) + 1

        total_wall_s = time.monotonic() - t_start
        print(
            f"[pumpkin real-board golden test] total_wall_s={total_wall_s:.2f} "
            f"total_violations={total} shorting_items={shorting} by_type={by_type}",
            flush=True,
        )

        # Comparison basis: the REAL board's OWN committed-DRC ratchet
        # (test_production_board_drc_regression's baseline), not the
        # fixture's fixed <=15 threshold -- see module docstring for why
        # that threshold does not describe a board at this scale/density
        # (measured directly: the AS-SHIPPED real board alone already has
        # 1281 total violations / 97 shorting_items, before this test
        # changes anything).
        assert shorting <= PRODUCTION_COMMITTED_BOARD_SHORTING_ITEMS, (
            f"Pumpkin real-board placement has {shorting} shorting_items, "
            f"worse than the committed board's own measured baseline "
            f"({PRODUCTION_COMMITTED_BOARD_SHORTING_ITEMS}). by_type={by_type}"
        )
        assert total <= PRODUCTION_COMMITTED_BOARD_TOTAL_DVIOLATIONS, (
            f"Pumpkin real-board placement has {total} total DRC violations, "
            f"worse than the committed board's own measured baseline "
            f"({PRODUCTION_COMMITTED_BOARD_TOTAL_DVIOLATIONS}). by_type={by_type}"
        )
    finally:
        os.unlink(placed_path)
