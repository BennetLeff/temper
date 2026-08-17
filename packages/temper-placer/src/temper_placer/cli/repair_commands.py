"""``temper-placer repair-unplaced`` -- add currently-unplaced component(s) to
a board and, if necessary, relocate already-placed neighbours by the minimum
amount required, honouring every hard placement constraint the CP-SAT
encoder already knows how to enforce.

**The gap this closes.** A spike (docs referenced in the task that produced
this module) established that the machinery to solve this class of problem
already existed --
``temper_placer.placer.cp_sat.fixed_copper`` (pad-vs-routed-copper
NoOverlap), ``domain_clearance`` (IEC 60335 clearance/creepage, including
the 8.0mm reinforced tier), ``isolation_barrier`` (the HV/SELV physical
corridor) and ``_encoder_solve.solve_placement``'s ``fixed_positions`` /
``minimize_displacement_to`` / ``max_displacement_mm`` minimal-disruption
API -- but nothing wired all of it together into one runnable path for "add
this component, and if it doesn't fit, tell me exactly what moved and by how
much, or exactly why nothing could work." This module is that wiring, not
new placement machinery: every constraint below delegates to the module that
already owns it.

**What this command does NOT do.** It does not route (a placement solve, not
a router); it does not touch ``pcb/temper.kicad_pcb`` (writes only to
``--output``, a caller-supplied scratch path); and it does not weaken any
clearance/creepage/isolation figure to make a solve succeed -- an UNSAT
result is reported as UNSAT, not worked around.

**Two-phase repair (issue #504's "minimal-disruption" shape).** Phase 1
freezes every component that is not one of ``--refs`` at its current board
position (``fixed_positions``) and solves for the free refs alone. If that
is infeasible and ``--displace`` names candidate neighbours, Phase 2
unfreezes exactly those refs with a bounded minimum-displacement objective
(``minimize_displacement_to`` + ``max_displacement_mm``, rotation pinned via
``fixed_rotations`` -- a rotation would move every pad of an already-routed
neighbour and disconnect its copper, which this tool does not re-route) and
re-solves. The command reports, for every ref, whether it moved and by how
much; if both phases fail, it reports the UNSAT core's constraint families
(fixed-copper / domain-clearance / isolation-barrier / geometry) named by
CP-SAT's own ``SufficientAssumptionsForInfeasibility``, not a guess.

**Why domain-clearance and keepaway constraints are filtered to the "touch
set".** ``generate_domain_clearance_constraints`` /
``generate_unclassified_hv_keepaway_constraints`` are queried over the
FULL component universe (so every relevant free-ref-vs-frozen-neighbour
pair is found) but the returned constraints are then filtered down to only
those touching a free or displaceable ref before being handed to the
solver. Constraints between two components that are BOTH frozen at their
existing board positions are dropped -- if a pre-existing pair of frozen
components already violates a domain-clearance minimum (a real, separately
tracked defect class on this board, unrelated to this command), re-adding
that pair as a hard constraint over positions this solve cannot change would
make the model trivially infeasible for a reason that has nothing to do
with the refs being placed. This mirrors the same reasoning
``fixed_positions``'s own docstring gives for freezing only the
"non-violating neighbourhood".

**Why the isolation barrier gets an empirical pre-flight, not a blind
include.** ``isolation_barrier.py``'s own module docstring records that the
CURRENT real board cannot have a compliant barrier drawn on it *at all* --
HV/SELV components interleave board-wide, independent of anything this
command does. Registering the barrier unconditionally over a solve that
freezes ~165 of 168 components at their current (already checkerboarded)
positions would make Phase 1 UNSAT for that pre-existing, unrelated reason
on every invocation, drowning out whatever this command's own refs are
actually blocked by. So this command first runs a cheap all-frozen
pre-flight (every real component pinned to its current position, barrier
constraint on) before deciding whether to include the barrier in the real
solve; the pre-flight's own verdict is printed either way, so a clean run
is distinguishable from "the barrier could not be verified against this
board's pre-existing layout" in the output, never silently dropped.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import click
from rich.panel import Panel
from rich.table import Table

from ._io import console


def _find_repo_file(relative_path: str) -> Path | None:
    """Locate a repo artifact by walking up from the current directory.

    Duplicated (not imported) from ``cli/__init__.py``'s private helper of
    the same name and behaviour: importing a leading-underscore name across
    CLI submodules is legal but couples two independently-evolving command
    modules to each other's internals for an eight-line helper -- not worth
    it. Keep both in sync if the discovery convention ever changes.
    """
    for candidate in (Path.cwd(), *Path.cwd().parents):
        p = candidate / relative_path
        if p.is_file():
            return p
    return None


def _rot_idx(quadrant_index: float | int | None) -> int:
    """Normalize a component's rotation to the solver's 0-3 quadrant index.

    ``Component.initial_rotation_quadrant`` (every call site's actual argument) is
    ALREADY the quantized 0-3 quadrant index -- ``io/_parse_modules.py``
    quantizes the real board angle at parse time, it is not degrees (an
    earlier version of this function divided by 90 here, silently treating
    an already-0-3 value as degrees: ``round(1/90) % 4 == 0`` for every
    input in {0,1,2,3} except 0 itself, i.e. it force-zeroed the rotation
    of every non-zero-rotated frozen/displaced component in
    ``fixed_positions``/``fixed_rotations`` -- pinning `rot_ref` to a
    DIFFERENT rotation than the one implied by that ref's own real,
    also-pinned x/y, an internally-contradictory footprint the encoder
    could only resolve by moving something, or by proving infeasible for a
    reason entirely unrelated to whatever else was being solved for; see
    ``docs/evidence/2026-08-13-courtyard-touch-set-filter.md``). This
    still tolerates a raw float / an out-of-range int by rounding and
    taking mod 4, so it is a safe no-op on an already-correct 0-3 int.
    """
    if quadrant_index is None:
        return 0
    return round(float(quadrant_index)) % 4


@dataclass
class _RepairPlan:
    free_refs: set[str]
    displace_refs: set[str]
    frozen_refs: set[str]
    touch_set: set[str]


def _build_plan(all_refs: set[str], free_refs: set[str], displace_refs: set[str]) -> _RepairPlan:
    unknown_free = free_refs - all_refs
    if unknown_free:
        raise click.ClickException(f"--refs names unknown component(s): {sorted(unknown_free)}")
    unknown_displace = displace_refs - all_refs
    if unknown_displace:
        raise click.ClickException(
            f"--displace names unknown component(s): {sorted(unknown_displace)}"
        )
    overlap = free_refs & displace_refs
    if overlap:
        raise click.ClickException(
            f"ref(s) named in both --refs and --displace: {sorted(overlap)}"
        )
    frozen_refs = all_refs - free_refs - displace_refs
    return _RepairPlan(
        free_refs=free_refs,
        displace_refs=displace_refs,
        frozen_refs=frozen_refs,
        touch_set=free_refs | displace_refs,
    )


def _rotated_half_extents(bounds: tuple[float, float], rot_idx: int) -> tuple[float, float]:
    """Courtyard half-width/half-height after the solver's quadrant rotation
    (rot 1/3 swap the local axes -- same convention as the CP-SAT model's
    own x_size/y_size rotation table, see fixed_copper.py's ``_rotated``)."""
    w, h = bounds
    return (h / 2.0, w / 2.0) if rot_idx % 2 == 1 else (w / 2.0, h / 2.0)


def _frozen_positions(
    comp_by_ref: dict, refs: set[str], *, clamp_warnings: list[str] | None = None
) -> dict[str, tuple[float, float, int]]:
    """Build the ``fixed_positions`` pin dict for *refs*.

    Clamps a ref's pinned centre so its courtyard box's start coordinate is
    never negative, in EITHER axis. This is not cosmetic: the CP-SAT
    model's own position variables (``CpSatModel.add_component``'s
    ``x_start``/``y_start``/``x_center``/etc.) are declared with a HARD
    ``NewIntVar(0, ...)`` domain floor of zero -- not an assumption-gated
    constraint, an actual variable-domain bound with no relaxation
    mechanism CP-SAT can report a core for. A ref whose REAL courtyard
    already extends past the board's own coordinate-frame origin by a
    fraction of a millimetre (measured: 12 of 168 components on
    ``pcb/temper.kicad_pcb`` as of 2026-08-13, e.g. C18 at x_start=-0.24mm)
    cannot be represented by ``fixed_positions`` at all without this --
    pinning it produces an immediate, silent (empty unsat_core, since no
    assumption governs a variable-domain violation), and completely
    unrelated INFEASIBLE for whatever else is being solved.

    Safe because this only affects the SOLVER's internal representation of
    a FROZEN (non-touch-set) ref for this one solve: the clamped value is
    never written back (``repair_unplaced`` only writes positions for
    ``plan.touch_set`` refs, via ``preserve_unmatched=True``), so the
    output board still carries this ref's true, unmodified position and
    rotation. The clamp is at most the sub-millimetre amount the real
    board already overhangs the origin by -- reported via
    *clamp_warnings* (when given) rather than applied silently.
    """
    out: dict[str, tuple[float, float, int]] = {}
    # `refs` is a set: iterate a stable order (ref name) rather than the
    # set's PYTHONHASHSEED-dependent iteration order, since that order
    # becomes this dict's insertion order (scripts/check_hash_order_determinism.py).
    for ref in sorted(refs):
        comp = comp_by_ref[ref]
        if comp.initial_position is None:
            raise click.ClickException(
                f"component {ref!r} has no board position to freeze at -- "
                "cannot build fixed_positions for it"
            )
        x, y = comp.initial_position
        rot = _rot_idx(getattr(comp, "initial_rotation_quadrant", 0))
        hw, hh = _rotated_half_extents(comp.bounds, rot)
        clamped_x, clamped_y = max(x, hw), max(y, hh)
        if (clamped_x, clamped_y) != (x, y) and clamp_warnings is not None:
            clamp_warnings.append(
                f"{ref}: courtyard start clamped to the solver's coordinate-frame "
                f"origin (real position ({x:.3f}, {y:.3f}) implies a start of "
                f"({x - hw:.3f}, {y - hh:.3f}), below the representable minimum of "
                "0 on at least one axis -- see _frozen_positions docstring)"
            )
        out[ref] = (clamped_x, clamped_y, rot)
    return out


def _domain_constraints(
    *,
    input_pcb: Path,
    manifest_path: Path,
    netlist_path: Path,
    all_refs: set[str],
    touch_set: set[str],
):
    """Generate the domain-clearance + unclassified-HV-keepaway HARD
    constraints, restricted to pairs touching the free/displaceable refs
    (see module docstring for why). Returns ``(constraints, stats)``.
    """
    from temper_placer.io.real_board import RealBoardUnavailable, load_real_board_placement
    from temper_placer.placer.cp_sat.domain_clearance import (
        generate_domain_clearance_constraints,
        generate_unclassified_hv_keepaway_constraints,
    )

    try:
        placement, voltage_domains, stats = load_real_board_placement(
            pcb_path=input_pcb, manifest_path=manifest_path, netlist_path=netlist_path
        )
    except RealBoardUnavailable as exc:
        raise click.ClickException(
            f"cannot build domain-clearance constraints: {exc} -- refusing to "
            "solve without the safety-clearance constraint family rather than "
            "silently solving unconstrained"
        ) from exc

    dc_all = generate_domain_clearance_constraints(placement, voltage_domains, all_refs)
    kw_all = generate_unclassified_hv_keepaway_constraints(placement, voltage_domains, all_refs)

    def _touches(c) -> bool:
        return c.a in touch_set or c.b in touch_set

    dc = [c for c in dc_all if _touches(c)]
    kw = [c for c in kw_all if _touches(c)]
    return dc + kw, {
        "domain_clearance_total": len(dc_all),
        "domain_clearance_kept": len(dc),
        "keepaway_total": len(kw_all),
        "keepaway_kept": len(kw),
        "real_board_stats": stats,
    }


def _isolation_barrier_preflight(
    *, netlist, board, manifest_path: Path, corridor_width_mm: float | None, orientation: str
) -> tuple[bool, str]:
    """All-frozen sanity check: with EVERY real component pinned to its
    current board position, is the barrier constraint itself satisfiable?

    This isolates "the barrier is unsatisfiable against the board's
    pre-existing, unrelated layout" (a known, separately-tracked condition
    per isolation_barrier.py's own module docstring) from "the barrier is
    unsatisfiable because of what THIS repair is trying to do" -- the two
    look identical from a bare infeasible/feasible verdict on the real solve
    alone. Returns (feasible, human-readable reason).
    """
    from temper_placer.placer.cp_sat.encoder import solve_placement

    comp_by_ref = {c.ref: c for c in netlist.components}
    all_refs = set(comp_by_ref)
    fixed_positions = _frozen_positions(comp_by_ref, all_refs)
    isolation_kwargs: dict = {"manifest_path": manifest_path, "orientation": orientation}
    if corridor_width_mm is not None:
        isolation_kwargs["corridor_width_mm"] = corridor_width_mm
    try:
        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=15_000,
            fixed_positions=fixed_positions,
            isolation_barrier=isolation_kwargs,
        )
    except Exception as exc:  # noqa: BLE001 -- pre-flight must never crash the command
        return False, f"pre-flight raised {type(exc).__name__}: {exc}"
    if result.status in ("optimal", "feasible"):
        return True, "the barrier already holds against the board's current, unmodified layout"
    names = sorted({u.get("name", "?") for u in result.unsat_core})
    return False, (
        f"barrier is UNSAT against the CURRENT board with every component frozen "
        f"(status={result.status}, unsat core names: {names or 'none reported'}) -- "
        "this is a pre-existing condition independent of --refs/--displace"
    )


def _print_solve_header(title: str) -> None:
    console.print(f"\n[bold cyan]{title}[/]")


def _print_unsat(result) -> None:
    if not result.unsat_core:
        console.print(f"  [red]status={result.status}[/] (no unsat core reported by the solver)")
        return
    lines = []
    for entry in result.unsat_core:
        lines.append(f"  • {entry.get('name', '?')}")
    console.print(
        Panel("\n".join(lines), title="UNSAT core (constraint families implicated)", border_style="red")
    )


@click.command(name="repair-unplaced")
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--refs",
    required=True,
    help="Comma-separated component refs to place (currently off-board / unplaced), e.g. T2,C37,R65.",
)
@click.option(
    "-o",
    "--output",
    required=True,
    type=click.Path(path_type=Path),
    help="Scratch output .kicad_pcb path for the candidate board. Must NOT be the tracked board.",
)
@click.option(
    "--displace",
    default="",
    help="Comma-separated already-placed refs allowed to move (bounded minimum-displacement) "
    "if the frozen-neighbourhood solve is infeasible. Default: none (nothing else moves).",
)
@click.option(
    "--max-displacement-mm",
    type=float,
    default=5.0,
    show_default=True,
    help="Hard Manhattan-distance bound on how far any --displace ref may move.",
)
@click.option(
    "--margin-mm",
    type=float,
    default=0.05,
    show_default=True,
    help="Pad-to-fixed-copper clearance margin (fixed_copper.py DEFAULT_MARGIN_MM).",
)
@click.option(
    "--isolation-barrier/--no-isolation-barrier",
    default=True,
    show_default=True,
    help="Honour the HV/SELV physical isolation barrier. A pre-flight check runs regardless; "
    "if the barrier is already UNSAT against the board's unmodified layout, it is "
    "automatically excluded from the real solve (reported, not silent).",
)
@click.option(
    "--isolation-orientation",
    type=click.Choice(["vertical", "horizontal"]),
    default="vertical",
    show_default=True,
)
@click.option("--isolation-corridor-width-mm", type=float, default=None)
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--netlist", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--timeout-ms", type=int, default=60_000, show_default=True)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option(
    "--auto-escalate/--no-auto-escalate",
    default=True,
    show_default=True,
    help="If the Phase-1 frozen-neighbourhood solve is infeasible and --displace is non-empty, "
    "automatically retry with those refs unfrozen (Phase 2).",
)
@click.option(
    "--fixed-copper/--no-fixed-copper",
    default=True,
    show_default=True,
    help="Diagnostic ablation: include the pad-vs-routed-copper NoOverlap constraint family. "
    "Disabling it is for attributing an UNSAT result to a specific constraint family -- "
    "never disable it to make a solve succeed.",
)
@click.option(
    "--domain-clearance/--no-domain-clearance",
    default=True,
    show_default=True,
    help="Diagnostic ablation: include the IEC 60335 domain-clearance/keepaway constraint "
    "family. Same caveat as --no-fixed-copper -- diagnostic only.",
)
@click.option(
    "--courtyard-touch-filter/--no-courtyard-touch-filter",
    default=True,
    show_default=True,
    help="Restrict the auto-generated courtyard SEPARATED constraint (the board-wide "
    "pairwise NoOverlap tau) to pairs touching --refs/--displace, the same way "
    "domain-clearance is filtered. WITHOUT this, a pair of two frozen, unrelated "
    "components that already violates courtyard clearance on the real board (measured: "
    "48 such pairs on pcb/temper.kicad_pcb, none involving the refs being placed) makes "
    "EVERY solve spuriously infeasible regardless of merit. Disabling this is diagnostic "
    "only -- to reproduce the unfiltered (bugged) behaviour, never to trust its verdict.",
)
@click.option(
    "--run-drc/--no-run-drc",
    default=True,
    show_default=True,
    help="Verify a feasible candidate with real kicad-cli DRC (pads vs. copper, not courtyards).",
)
@click.option("--unsat-report", type=click.Path(path_type=Path), default=None)
def repair_unplaced(
    input_pcb: Path,
    refs: str,
    output: Path,
    displace: str,
    max_displacement_mm: float,
    margin_mm: float,
    isolation_barrier: bool,
    isolation_orientation: str,
    isolation_corridor_width_mm: float | None,
    manifest: Path | None,
    netlist: Path | None,
    timeout_ms: int,
    seed: int,
    auto_escalate: bool,
    fixed_copper: bool,
    domain_clearance: bool,
    courtyard_touch_filter: bool,
    run_drc: bool,
    unsat_report: Path | None,
) -> None:
    """Place currently-unplaced component(s) onto a board, with minimum-
    displacement repair of neighbours if nothing else fits.

    INPUT_PCB: the board to solve against (e.g. pcb/temper.kicad_pcb). Never
    written to -- only OUTPUT is.

    Example:

        temper-placer repair-unplaced pcb/temper.kicad_pcb \\
            --refs T2,C37,R65 --displace R30,C27 \\
            --max-displacement-mm 5.0 -o /tmp/candidate.kicad_pcb
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.placer.cp_sat.encoder import solve_placement

    repo_pcb = _find_repo_file("pcb/temper.kicad_pcb")
    if repo_pcb is not None and output.resolve() == repo_pcb.resolve():
        raise click.ClickException(
            f"refusing to write to {output} -- it resolves to the tracked board "
            f"({repo_pcb}). This command only ever writes scratch candidates."
        )

    manifest_path = manifest or _find_repo_file("elec/domain_manifest.yaml")
    netlist_path = netlist or _find_repo_file("elec/build/default.net")
    if manifest_path is None:
        raise click.ClickException(
            "elec/domain_manifest.yaml not found (run from the repo root)"
        )
    if netlist_path is None:
        raise click.ClickException(
            "elec/build/default.net not found -- run `make netlist` first"
        )

    console.print(
        Panel.fit(
            f"[bold blue]temper-placer repair-unplaced[/]\n{input_pcb}", border_style="blue"
        )
    )

    parse_result = parse_kicad_pcb(input_pcb)
    pl_netlist = parse_result.netlist
    board = parse_result.board
    comp_by_ref = {c.ref: c for c in pl_netlist.components}
    all_refs = set(comp_by_ref)

    free_refs = {r.strip() for r in refs.split(",") if r.strip()}
    displace_refs = {r.strip() for r in displace.split(",") if r.strip()}
    plan = _build_plan(all_refs, free_refs, displace_refs)

    console.print(
        f"  {len(plan.free_refs)} free ref(s): {sorted(plan.free_refs)}\n"
        f"  {len(plan.displace_refs)} displaceable ref(s): {sorted(plan.displace_refs) or 'none'}\n"
        f"  {len(plan.frozen_refs)} frozen ref(s) (unchanged)"
    )

    extra_constraints: list = []
    if domain_clearance:
        extra_constraints, dc_stats = _domain_constraints(
            input_pcb=input_pcb,
            manifest_path=manifest_path,
            netlist_path=netlist_path,
            all_refs=all_refs,
            touch_set=plan.touch_set,
        )
        console.print(
            f"  domain-clearance: {dc_stats['domain_clearance_kept']}/"
            f"{dc_stats['domain_clearance_total']} constraint(s) touch the free/displaceable "
            f"set; keepaway: {dc_stats['keepaway_kept']}/{dc_stats['keepaway_total']}"
        )
    else:
        console.print("  [yellow]domain-clearance constraint family DISABLED (diagnostic ablation)[/]")

    if courtyard_touch_filter:
        console.print(
            "  courtyard constraint: filtered to the free/displaceable set (default) -- "
            "pre-existing frozen-vs-frozen courtyard violations elsewhere on the board "
            "cannot cause a spurious UNSAT here"
        )
    else:
        console.print(
            "  [yellow]courtyard constraint UNFILTERED (diagnostic ablation) -- pre-existing "
            "frozen-vs-frozen violations elsewhere on the board CAN cause a spurious UNSAT; "
            "do not trust an UNSAT verdict produced this way[/]"
        )

    fixed_copper_kwargs = None
    if fixed_copper:
        fixed_copper_kwargs = {
            "parse_result": parse_result,
            "free_refs": plan.touch_set,
            "margin_mm": margin_mm,
            "include_other_pads": True,
        }
    else:
        console.print("  [yellow]fixed-copper constraint family DISABLED (diagnostic ablation)[/]")

    use_barrier = False
    isolation_kwargs: dict | None = None
    if isolation_barrier:
        _print_solve_header("Isolation-barrier pre-flight (all components frozen)")
        preflight_ok, preflight_reason = _isolation_barrier_preflight(
            netlist=pl_netlist,
            board=board,
            manifest_path=manifest_path,
            corridor_width_mm=isolation_corridor_width_mm,
            orientation=isolation_orientation,
        )
        console.print(f"  {'[green]OK[/]' if preflight_ok else '[yellow]SKIPPED[/]'}: {preflight_reason}")
        if preflight_ok:
            use_barrier = True
            isolation_kwargs = {"manifest_path": manifest_path, "orientation": isolation_orientation}
            if isolation_corridor_width_mm is not None:
                isolation_kwargs["corridor_width_mm"] = isolation_corridor_width_mm
        else:
            console.print(
                "  [yellow]Isolation barrier excluded from this solve[/] -- pre-existing "
                "condition unrelated to --refs/--displace (see reason above)."
            )

    # ------------------------------------------------------------------
    # Phase 1: freeze everything except the free refs.
    # ------------------------------------------------------------------
    _print_solve_header("Phase 1: solve free refs only, every neighbour frozen")
    phase1_frozen = plan.frozen_refs | plan.displace_refs
    clamp_warnings: list[str] = []
    fixed_positions_1 = _frozen_positions(comp_by_ref, phase1_frozen, clamp_warnings=clamp_warnings)
    if clamp_warnings:
        console.print(
            f"  [dim]{len(clamp_warnings)} frozen ref(s) clamped to the solver's "
            "representable coordinate frame (sub-mm, solver-internal only -- "
            "see repair_commands._frozen_positions):[/] "
            f"{', '.join(w.split(':')[0] for w in clamp_warnings)}"
        )
    result = solve_placement(
        netlist=pl_netlist,
        board=board,
        extra_constraints=extra_constraints,
        timeout_ms=timeout_ms,
        seed=seed,
        fixed_positions=fixed_positions_1,
        fixed_copper=fixed_copper_kwargs,
        isolation_barrier=isolation_kwargs if use_barrier else None,
        auto_pairwise_touch_refs=plan.touch_set if courtyard_touch_filter else None,
    )
    console.print(f"  status={result.status} ({result.solve_time_ms:.0f}ms)")
    phase_used = 1
    displaced: dict[str, tuple[float, float, float]] = {}

    if result.status not in ("optimal", "feasible"):
        _print_unsat(result)
        if auto_escalate and plan.displace_refs:
            _print_solve_header(
                f"Phase 2: unfreeze {sorted(plan.displace_refs)} "
                f"(bounded minimum displacement, max {max_displacement_mm}mm)"
            )
            fixed_positions_2 = _frozen_positions(comp_by_ref, plan.frozen_refs)  # clamp_warnings already surfaced above
            minimize_to = {
                ref: (comp_by_ref[ref].initial_position[0], comp_by_ref[ref].initial_position[1])
                for ref in plan.displace_refs
            }
            fixed_rotations = {
                ref: _rot_idx(getattr(comp_by_ref[ref], "initial_rotation_quadrant", 0))
                for ref in plan.displace_refs
            }
            result = solve_placement(
                netlist=pl_netlist,
                board=board,
                extra_constraints=extra_constraints,
                timeout_ms=timeout_ms,
                seed=seed,
                fixed_positions=fixed_positions_2,
                minimize_displacement_to=minimize_to,
                max_displacement_mm=max_displacement_mm,
                fixed_rotations=fixed_rotations,
                fixed_copper=fixed_copper_kwargs,
                isolation_barrier=isolation_kwargs if use_barrier else None,
                auto_pairwise_touch_refs=plan.touch_set if courtyard_touch_filter else None,
            )
            console.print(f"  status={result.status} ({result.solve_time_ms:.0f}ms)")
            phase_used = 2
            if result.status in ("optimal", "feasible"):
                for ref in plan.displace_refs:
                    ox, oy = comp_by_ref[ref].initial_position
                    nx, ny = result.positions[ref]
                    dist = abs(nx - ox) + abs(ny - oy)
                    if dist > 1e-6:
                        displaced[ref] = (nx - ox, ny - oy, dist)
            else:
                _print_unsat(result)
        elif not plan.displace_refs:
            console.print(
                "  [yellow]No --displace candidates given -- not escalating.[/] Pass "
                "--displace with candidate neighbour refs to try minimum-displacement repair."
            )

    if result.status not in ("optimal", "feasible"):
        console.print(
            Panel.fit(
                f"[bold red]UNSAT[/] after phase {phase_used} -- no legal placement found "
                f"for {sorted(plan.free_refs)}"
                + (f" even allowing {sorted(plan.displace_refs)} to move" if phase_used == 2 else ""),
                border_style="red",
            )
        )
        if unsat_report is not None:
            import json as _json

            unsat_report.write_text(_json.dumps(result.unsat_core, indent=2), encoding="utf-8")
            console.print(f"  UNSAT report written to: {unsat_report}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Feasible: report positions, write the scratch candidate, verify DRC.
    # ------------------------------------------------------------------
    console.print(Panel.fit(f"[bold green]SAT[/] (phase {phase_used})", border_style="green"))

    table = Table(title="Newly placed")
    table.add_column("ref")
    table.add_column("x (mm)")
    table.add_column("y (mm)")
    table.add_column("rotation")
    for ref in sorted(plan.free_refs):
        x, y = result.positions[ref]
        rot = result.rotations.get(ref, 0) * 90.0
        table.add_row(ref, f"{x:.3f}", f"{y:.3f}", f"{rot:.0f}")
    console.print(table)

    if displaced:
        dtable = Table(title="Neighbours moved (minimum-displacement repair)")
        dtable.add_column("ref")
        dtable.add_column("dx (mm)")
        dtable.add_column("dy (mm)")
        dtable.add_column("distance (mm)")
        for ref, (dx, dy, dist) in sorted(displaced.items()):
            dtable.add_row(ref, f"{dx:+.3f}", f"{dy:+.3f}", f"{dist:.3f}")
        console.print(dtable)
    elif phase_used == 2:
        console.print(
            "  [dim]Phase 2 ran but every --displace ref settled back at its original "
            "position (0mm net displacement).[/]"
        )

    from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb

    placements: dict[str, PlacementUpdate] = {}
    for ref in plan.touch_set:
        if ref not in result.positions:
            continue
        x, y = result.positions[ref]
        placements[ref] = PlacementUpdate(
            ref=ref, x=x, y=y, rotation=result.rotations.get(ref, 0) * 90.0
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    write_result = write_placements_to_pcb(
        template_pcb=input_pcb,
        output_pcb=output,
        placements=placements,
        preserve_unmatched=True,
        components=pl_netlist.components,
        board_origin=board.origin,
    )
    console.print(
        f"  [green]Wrote[/] {write_result.components_updated} updated component(s) to {output}"
    )
    for w in write_result.warnings:
        console.print(f"  [yellow]warning:[/] {w}")

    if not run_drc:
        return

    _print_solve_header("Real kicad-cli DRC verification (pads vs. copper, not courtyards)")
    # Aliased on import: the `--run-drc/--no-run-drc` CLI flag above binds to
    # a same-named local `run_drc: bool`, so importing the *function*
    # `run_drc` under its own name would shadow that parameter -- it works
    # at runtime (the boolean's only remaining use, the early-return above,
    # already ran), but it reads as a type error to mypy (which infers one
    # static type per local name across the function) and to a human
    # skimming the diff.
    from temper_placer.validation._drc_api import (
        DrcRunnerError,
        copy_kicad_project_sidecar,
        run_drc as run_kicad_drc,
    )

    try:
        copy_kicad_project_sidecar(output, input_pcb)
        drc_result = run_kicad_drc(output)
    except DrcRunnerError as exc:
        console.print(f"  [red]DRC could not run:[/] {exc}")
        sys.exit(2)

    by_rule: dict[str, int] = {}
    touching_moved: list = []
    for err in drc_result.errors:
        by_rule[err.rule] = by_rule.get(err.rule, 0) + 1
        if set(err.components) & plan.touch_set:
            touching_moved.append(err)

    console.print(
        f"  Candidate DRC: {drc_result.error_count} error(s), {drc_result.warning_count} warning(s)"
    )
    if by_rule:
        rtable = Table(title="DRC errors by rule")
        rtable.add_column("rule")
        rtable.add_column("count")
        for rule, count in sorted(by_rule.items(), key=lambda kv: -kv[1]):
            rtable.add_row(rule, str(count))
        console.print(rtable)

    console.print(
        f"  [{'red' if touching_moved else 'green'}]"
        f"{len(touching_moved)} error(s) directly name a moved/placed component[/]"
    )
    for err in touching_moved[:20]:
        console.print(f"    [red]{err.rule}[/]: {err.message} ({', '.join(err.components)})")
