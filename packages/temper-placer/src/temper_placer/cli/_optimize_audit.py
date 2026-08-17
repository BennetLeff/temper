"""``optimize`` command's post-solve audit wiring: input construction and
report printing for the REQ-SAFE-01 validator audit, the F.Fab body-collision
audit, the tank-node creepage report, and UNSAT-core surfacing.

Split out of ``cli/__init__.py`` (LOC cap, R3): these seven functions are a
self-contained concern -- they build the optional audit inputs
``solve_placement`` accepts and print whatever audit buckets a solve result
carries -- independent of the CLI dispatcher's own job (subcommand
registration). No behavior change; only the module boundary moved. Every
name here remains importable as ``temper_placer.cli.<name>`` via the
re-export in ``cli/__init__.py``, so existing callers (docs/evidence probe,
tests/cli/test_unsat_report.py, monkeypatch call sites) are unaffected.
"""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from ._io import console


def _find_repo_file(relative_path: str) -> Path | None:
    """Locate a repo artifact (``elec/domain_manifest.yaml`` or
    ``elec/build/default.net``) by walking up from the current directory.

    The CLI's existing convention is repo-root-relative paths; walking up
    makes the audit wiring work from subdirectories (e.g. running from
    ``packages/temper-placer``) without inventing a new config surface.
    Returns None when not found (the caller logs the audit skip).
    """
    for candidate in (Path.cwd(), *Path.cwd().parents):
        p = candidate / relative_path
        if p.is_file():
            return p
    return None


def _build_validator_input(input_pcb: Path) -> dict | None:
    """Construct ``solve_placement``'s ``validator_input`` from the real board.

    Issue #617 second half: the optimize command builds only
    netlist/board/constraints; the validator-shape placement + voltage-domain
    map the REQ-SAFE-01 post-solve audit needs now come from the production
    loader ``temper_placer.io.real_board`` (hoisted out of the test fixture so
    this path can construct them).

    Returns None -- and logs why -- when the audit inputs are unavailable
    (missing ``pcb/``/``elec/build/default.net``/``elec/domain_manifest.yaml``,
    or a board with zero domain-classified components). The audit is additive;
    an absent ``validator_input`` is the encoder's documented skip, so the
    solve proceeds byte-identical to the pre-wiring behavior. The
    ValueError-on-missing-keys contract is respected by construction: we only
    return a dict carrying BOTH ``placement`` and ``voltage_domains``.
    """
    from temper_placer.io.real_board import RealBoardUnavailable, load_real_board_placement

    manifest_path = _find_repo_file("elec/domain_manifest.yaml")
    netlist_path = _find_repo_file("elec/build/default.net")
    if manifest_path is None or netlist_path is None:
        missing = "elec/domain_manifest.yaml" if manifest_path is None else "elec/build/default.net"
        console.print(
            f"[yellow]REQ-SAFE-01 validator post-solve audit SKIPPED: {missing} "
            "not found (run from the repo root; run `make netlist` first). "
            "The solve runs unaudited.[/]"
        )
        return None

    try:
        placement, voltage_domains, _stats = load_real_board_placement(
            pcb_path=input_pcb,
            manifest_path=manifest_path,
            netlist_path=netlist_path,
        )
    except RealBoardUnavailable as exc:
        console.print(
            f"[yellow]REQ-SAFE-01 validator post-solve audit SKIPPED: {exc}"
            " (audit inputs unavailable; solve runs unaudited)[/]"
        )
        return None

    if not placement.get("components"):
        console.print(
            "[yellow]REQ-SAFE-01 validator post-solve audit SKIPPED: the board "
            "has zero domain-classified components -- re-running the validator "
            "on it would vacuous-pass (solve runs unaudited)[/]"
        )
        return None

    console.print(
        f"  [cyan]REQ-SAFE-01 validator audit armed[/]: "
        f"{len(placement['components'])} classified component(s), "
        f"{len(voltage_domains)} classified net(s)"
    )
    return {"placement": placement, "voltage_domains": voltage_domains}


def _build_domain_clearance_constraints(validator_input: dict | None, all_refs: set) -> list:
    """Build the full-board IEC 60335 PD3 domain-clearance SEPARATED
    constraint set from the same real-board placement + voltage-domain map
    ``validator_input`` already loads for the post-solve audit.

    Per docs/evidence/2026-08-17-placer-creepage-constraint-spike.md: this
    generator (``placer.cp_sat.domain_clearance.generate_domain_clearance_constraints``)
    already carries the correct 12.6mm PD3 figure and the correct classifier
    (``elec/domain_manifest.yaml`` via the same ``load_real_board_placement``
    loader ``_build_validator_input`` above already calls) but, before this,
    was wired into exactly one caller: ``cli/repair_commands.py``'s narrow
    single/few-component ``repair-unplaced`` command. It was never part of
    the constraint set the main ``optimize`` command (``--loop`` or
    ``--no-loop``) solves against, so PD3 creepage/clearance was enforced
    only as a post-hoc, already-routed-board DRC verdict -- discovered net
    by net, after the router had already spent time on nets that could
    never legally connect (the J1/K1 case the spike documents).

    Returns [] -- logging nothing extra beyond what ``_build_validator_input``
    already logged -- when ``validator_input`` is unavailable (the same skip
    condition), so an absent real-board input leaves ``extra_constraints``
    unchanged: additive, no behavior change, matching every other optional
    solve input in this module.

    ``all_refs`` MUST be every component ref in the netlist being solved,
    not a subset scoped to a currently-diagnosed violation -- the spike
    (§6, citing docs/evidence/2026-07-30-copper-aware-domain-resolve.md §2)
    measured scoping to only known-violating pairs as unsound: it left every
    other pair unconstrained and CP-SAT was then free to drift previously-
    compliant components elsewhere on the board while satisfying the
    explicit subset, regressing total REQ-SAFE-01 violations 76->217-265 on
    a comparable board state. The full classified cross-domain pair set is
    encoded on every solve for exactly this reason.
    """
    if validator_input is None:
        return []

    from temper_placer.placer.cp_sat.domain_clearance import (
        generate_domain_clearance_constraints,
    )

    constraints = generate_domain_clearance_constraints(
        validator_input["placement"], validator_input["voltage_domains"], all_refs
    )
    console.print(
        f"  [cyan]Domain-clearance (IEC 60335 PD3) armed[/]: "
        f"{len(constraints)} constraint(s) over {len(all_refs)} component(s) "
        "(full classified cross-domain pair set, not violation-scoped)"
    )
    return constraints


def _print_validator_audit(result: object, indent: str = "  ") -> None:
    """Surface the validator post-solve audit buckets when a solve carried
    ``validator_input`` (additive reporting; absent audit = no output)."""
    audit = getattr(result, "validator_audit", None)
    if audit is None:
        return
    console.print(
        f"{indent}REQ-SAFE-01 validator post-solve audit: "
        f"{len(audit.hard_failures)} hard, "
        f"{len(audit.intra_footprint)} intra-footprint, "
        f"{len(audit.coverage_gaps)} coverage-gap "
        f"(geometry_trusted={audit.geometry_trusted})"
    )


def _build_body_collision_input(input_pcb: Path) -> dict | None:
    """Construct ``solve_placement``'s ``body_collision_input`` from the
    real board -- arms the fail-closed ``F.Fab`` body-collision post-solve
    audit (see ``placer.cp_sat.body_collision``).

    Returns None -- and logs why -- when the audit inputs are unavailable
    (the pinned allowlist config is missing, or the board carries no
    parseable ``F.Fab`` geometry at all). The audit is additive; an absent
    ``body_collision_input`` is the encoder's documented skip, so the solve
    proceeds byte-identical to the pre-wiring behavior -- but this is the
    ONE production call site, so in normal operation this is always armed,
    same posture as ``_build_validator_input``.
    """
    from temper_placer.io.fab_body_extraction import extract_fab_bodies
    from temper_placer.placer.cp_sat.body_collision import load_body_collision_allowlist

    allowlist_path = _find_repo_file("packages/temper-placer/configs/body_collision_allowlist.yaml")
    if allowlist_path is None:
        console.print(
            "[yellow]F.Fab body-collision post-solve audit SKIPPED: "
            "packages/temper-placer/configs/body_collision_allowlist.yaml not "
            "found (run from the repo root). The solve runs unaudited for "
            "body collisions.[/]"
        )
        return None

    try:
        allowlist = load_body_collision_allowlist(allowlist_path)
        fab_bodies = extract_fab_bodies(input_pcb)
    except (FileNotFoundError, ValueError) as exc:
        console.print(
            f"[yellow]F.Fab body-collision post-solve audit SKIPPED: {exc} "
            "(audit inputs unavailable; solve runs unaudited)[/]"
        )
        return None

    if not fab_bodies:
        console.print(
            "[yellow]F.Fab body-collision post-solve audit SKIPPED: no "
            "component on the input board carries parseable F.Fab geometry "
            "-- re-running the audit would vacuous-pass (solve runs "
            "unaudited)[/]"
        )
        return None

    console.print(
        f"  [cyan]F.Fab body-collision audit armed[/]: "
        f"{len(fab_bodies)} component(s) with body geometry, "
        f"{len(allowlist)} pre-existing collision(s) allowlisted"
    )
    return {"fab_bodies": fab_bodies, "allowlist": allowlist}


def _print_body_collision_audit(result: object, indent: str = "  ") -> None:
    """Surface the body-collision post-solve audit when a solve carried
    ``body_collision_input`` (additive reporting; absent audit = no
    output). A non-empty ``violations`` list never reaches here -- it
    raises inside ``solve_placement`` -- so this only ever reports the
    allowlisted (unchanged-or-better) pre-existing debt a clean solve
    carried forward."""
    audit = getattr(result, "body_collision_audit", None)
    if audit is None:
        return
    console.print(
        f"{indent}F.Fab body-collision post-solve audit: 0 violations, "
        f"{len(audit.allowlisted)} allowlisted pre-existing collision(s) over "
        f"{audit.checked_pairs} checked pair(s)"
    )


def _print_tank_creepage_report(result: object, indent: str = "  ") -> None:
    """Surface what the tank-node creepage constraint actually encoded.

    The self-pair line is the load-bearing half: those are intra-footprint
    pad pairs (R30's two litz terminals, the tank caps' own two pads) that
    NO placement constraint can separate, because a component's pads move
    as one rigid body. They are fixed in the footprint library, not by the
    solver, and printing them here keeps that gap visible on every
    production solve instead of only in the module's WARNING log.
    """
    report = getattr(result, "tank_creepage_report", None)
    if report is None:
        return
    console.print(
        f"{indent}Tank-node creepage: {report.pairs_encoded} pair(s) encoded at "
        f"{report.margin_mm}mm ({len(report.tank_refs)} tank x {len(report.other_refs)} "
        f"other-HV, {report.pairs_skipped_absent} skipped as absent)"
    )
    if report.self_pairs:
        console.print(
            f"{indent}  [yellow]NOT covered (intra-footprint, fix in the footprint "
            f"library):[/] {', '.join(report.self_pairs)}"
        )


def _maybe_surface_unsat(result: object, unsat_report_path: Path | None) -> None:
    """Surface UNSAT report if the result carries one.

    Handles both CpSatPlacementResult.unsat_core (list of {name, because})
    and UnsatReport dataclass from the F4 acceptance gate workstream.
    """
    if result is None:
        return

    unsat = getattr(result, "unsat_report", None) or getattr(result, "unsat_core", None)
    if not unsat:
        return

    # Handle simplified unsat_core list from CpSatPlacementResult.
    if isinstance(unsat, list) and unsat:
        console.print(
            Panel(
                "\n".join(
                    f"  • {e.get('name', '?')}"
                    + (f"\n    because: {e['because']}" if e.get("because") else "")
                    for e in unsat
                ),
                border_style="red",
                title="UNSAT Core",
            ),
            style="",
        )
        if unsat_report_path is not None:
            import json as _json

            unsat_report_path.write_text(_json.dumps(unsat, indent=2), encoding="utf-8")
            console.print(f"[yellow]UNSAT report written to:[/] {unsat_report_path}")
        return

    try:
        from temper_placer.placer.cp_sat.unsat_surface import (
            format_unsat_panel,
            write_unsat_json,
        )

        console.print(
            Panel(format_unsat_panel(unsat), border_style="red", title="UNSAT Core"),
            style="",
        )

        if unsat_report_path is not None:
            write_unsat_json(unsat, unsat_report_path)
            console.print(f"[yellow]UNSAT report written to:[/] {unsat_report_path}")
    except ImportError:
        console.print("[red]Failed to import UNSAT surface module.[/]")
