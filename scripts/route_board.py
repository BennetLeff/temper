#!/usr/bin/env python3
"""Route a KiCad PCB through the router_v6 production entry point.

This is now the only routing entry point, and ``make route`` invokes it.
It was written because the two things that claimed that role were not
doing it: ``make route`` targeted the 33-net benchmark fixture
(``pcb/benchmarks/temper_fixture_33.kicad_pcb``) rather than the
production board, and ``scripts/internal_route.py`` imported the
superseded ``temper_placer.routing.*`` tree plus an undeclared ``jax``
dependency and could not be imported at all. Both have since been
resolved in this script's favour: the ``make route`` target was
re-pointed at it (2026-08-04, and at ``pcb/temper.kicad_pcb``), and
``internal_route.py`` was RETIREd as import-dead and deleted the same day
(``docs/evidence/2026-08-04-wave4-residual-verdicts.md``).

The live API is ``temper_placer.router_v6.adapter.route_pcb``, the same
call used to produce the committed route in ``556ccf4f`` and the one
``test_production_board_routing_drc_regression`` exercises as a CI gate.
See ``docs/evidence/2026-07-27-first-route-and-profile.md`` for how this
call path was originally derived.

Usage:
    # Route the production board once, writing the result to a review path.
    # Never writes pcb/temper.kicad_pcb itself -- --output is mandatory and
    # is refused if it resolves to the same path as --pcb.
    uv run python3 scripts/route_board.py --output /tmp/temper_routed.kicad_pcb

    # Measure run-to-run completion variance (writes nothing to disk).
    uv run python3 scripts/route_board.py --runs 5

Report fields (both modes): completion (routed/attempted nets), segment,
via, and zone counts (grep-equivalent substring counts on the routed
content), and wall time. Zones are U3's regenerated pours (R7) -- the
board fed to route_pcb has its committed zones stripped first (see
strip_existing_copper in temper_io_types), so any
zones present in the output are this run's own regenerated output, never
carried-over stale input.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PCB = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_RULES = (
    REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
)


def _make_parsed_stub(pcb_path: Path, netlist: Any) -> Any:
    """Minimal ``route_pcb(parsed=...)`` stub -- must carry .source_path and .nets.

    A stub built without ``.nets`` silently disables netclass-SSOT
    layer-constraint resolution (every net silently stays on its default
    layer, no error raised). This mirrors
    ``packages/temper-placer/tests/conftest.py::make_parsed_pcb_stub`` --
    see
    docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md
    for why a bare stub is the wrong shortcut here.
    """
    return type(
        "ParsedStub", (), {"source_path": pcb_path, "nets": netlist.nets}
    )()


def strip_existing_copper(content: str) -> tuple[str, int]:
    """Remove committed (segment ...), (via ...), and (zone ...) blocks.

    U3 (R7): thin re-export of the shared, paren-balanced implementation in
    ``temper_io_types`` -- kept as a module-level name
    here (rather than only inlined in ``route_once``) so this remains
    directly importable/testable as ``route_board.strip_existing_copper``,
    matching this script's prior art. The import itself is deferred inside
    this function body, not hoisted to module scope: importing any
    ``temper_placer.router_v6`` submodule executes that package's full
    ``__init__.py`` (the Rust router extension, etc.), which this
    script otherwise avoids paying for argument parsing / ``--help``.

    Previously this was its own single-line ``re.MULTILINE`` regex matching
    only ``(segment ...)``/``(via ...)`` -- a pattern that could never have
    matched a ``(zone ...)`` block, which is not single-line (see
    ``pcb/temper.kicad_pcb``: every zone spans dozens of lines --
    ``priority``, ``connect_pads``, ``min_thickness``, ``fill``, and a
    nested ``(polygon (pts (xy ..) ...))``). That is why every "clean"
    re-route still inherited all 96 committed zones.
    """
    from temper_io_types import (
        strip_existing_copper as _strip_existing_copper,
    )

    return _strip_existing_copper(content)


def audit_pad_connectivity(
    content: str, net_pins: dict[str, list[tuple[str, str]]] | None = None
) -> dict[str, Any]:
    """Run ``pad_connectivity_audit`` against routed ``.kicad_pcb`` content
    and return a compact, JSON-serializable summary.

    This is the PRIMARY completion metric (docs/evidence/
    2026-08-08-nlayer-via-astar-spike.md): ``nets_carrying_copper()`` /
    the routed/attempted line above only prove a net has SOME copper with
    the right net number -- not that the copper actually reaches every one
    of that net's own pads. A net can be "carrying copper" and still have
    most of its pads unreached (the documented b39b382d shape); measured on
    this board, a 32-net rise in raw "carrying copper" was proven to be
    entirely this shape -- zero of those nets became genuinely
    pad-connected (see the evidence doc §3.3). Surfacing the pad-connected
    count here, in the router's own normal output, is what makes that kind
    of regression visible without a separate manual audit step.

    ``audit_pcb_file`` parses a real ``.kicad_pcb`` path (it needs the full
    KiCad footprint/pin structure to resolve pad positions the same way the
    router itself does), so ``content`` is written to a throwaway temp file
    first.

    ``net_pins``, when supplied (``{net_name: [(component_ref, pin_name),
    ...]}``, i.e. ``Net.pins`` per net), additionally runs
    ``find_pin_identity_pad_mismatches`` -- the accounting guard for a net
    whose ``(component_ref, pin_name)`` identity view collapses to <=1
    distinct pin while its real, ground-truth physical pad count is > 1
    (K2/K3's manufacturer-duplicated relay contact pads,
    ``discharge.k_dis1-no``/``discharge.k_dis2-no`` being the measured
    real example -- see ``pad_connectivity_audit.find_pin_identity_pad_mismatches``'s
    docstring). Surfaced here so the actual production entry point this
    task names (``route_board.py --net-batching --batch-size 10``) reports
    the same discrepancy the standalone CI gate
    (``check_net_pin_identity_pad_correspondence.py``) checks, not only a
    separate script someone has to remember to run.
    """
    from temper_placer.router_v6.pad_connectivity_audit import (
        audit_pcb_file,
        find_pin_identity_pad_mismatches,
    )

    with tempfile.NamedTemporaryFile(
        "w", suffix=".kicad_pcb", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        results = audit_pcb_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    fully_connected_nets = sorted(n for n, r in results.items() if r.fully_connected)
    fake_completion_nets = sorted(n for n, r in results.items() if r.is_fake_completion)
    honest_gap = len(results) - len(fully_connected_nets) - len(fake_completion_nets)

    pin_identity_mismatches = (
        find_pin_identity_pad_mismatches(net_pins, results) if net_pins else []
    )

    return {
        "audited": len(results),
        "fully_connected": len(fully_connected_nets),
        "fully_connected_nets": fully_connected_nets,
        "fake_completion": len(fake_completion_nets),
        "fake_completion_nets": fake_completion_nets,
        "honest_gap": honest_gap,
        "pin_identity_mismatches": pin_identity_mismatches,
    }


def route_once(
    pcb_path: Path,
    rules_path: Path,
    *,
    keep_existing_copper: bool = False,
    enable_geographic_pruning: bool = False,
    enable_net_batching: bool = False,
    net_batch_size: int = 10,
    max_sat_nets: int | None = None,
    enable_nlayer_astar_spike: bool = False,
) -> dict[str, Any]:
    """Run one full route_pcb() pass and return measured results.

    Component positions come from the board itself (an empty placements dict
    means "route with existing board positions" -- see _adapter_convert.py:214).

    By default existing copper -- segments, vias, AND zones -- is stripped
    first, so the run measures routing the board from scratch and is
    comparable with the committed route. Pass keep_existing_copper=True to
    route on top of what is already there.
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.router_v6.adapter import route_pcb

    rules = load_netclass_rules(rules_path)
    netlist = parse_kicad_pcb(pcb_path).netlist

    stripped_count = 0
    route_src = pcb_path
    tmp_clean = None
    if not keep_existing_copper:
        content = pcb_path.read_text(encoding="utf-8")
        cleaned, stripped_count = strip_existing_copper(content)
        tmp_clean = tempfile.NamedTemporaryFile(
            "w", suffix=".kicad_pcb", delete=False, encoding="utf-8"
        )
        tmp_clean.write(cleaned)
        tmp_clean.close()
        route_src = Path(tmp_clean.name)

    parsed_stub = _make_parsed_stub(route_src, netlist)

    t0 = time.perf_counter()
    result = route_pcb(
        parsed_stub,
        {},
        design_rules=rules.design_rules,
        # enable_manufacturing_drc stays at its False default deliberately --
        # it is reporting-only, does not affect pathfinding, and the full
        # DFM bundle costs ~6-7x routing wall time (see
        # docs/evidence/2026-07-26-manufacturing-drc-scalability.md).
        enable_geographic_pruning=enable_geographic_pruning,
        enable_net_batching=enable_net_batching,
        net_batch_size=net_batch_size,
        max_sat_nets=max_sat_nets,
        enable_nlayer_astar_spike=enable_nlayer_astar_spike,
    )
    wall_s = time.perf_counter() - t0

    content = result.routed_pcb_content or ""
    segments = content.count("(segment ")
    vias = content.count("(via ")
    zones = content.count("(zone ")

    # Topology-level ("Stage 3 solved") vs copper-level ("Stage 4 + zone
    # regen actually emitted geometry") outcome, cross-checked -- see
    # temper_placer.router_v6.topology_copper_audit's module docstring.
    # This is the check that makes net_batching's "N/110 nets fell back"
    # trace line (topology-only) unable to read fully green while nets
    # silently emit no copper: the two are now reported side by side.
    copper_audit_report = ""
    unexplained_copper_gap: list[str] = []
    if content and result.topology_solved_nets:
        from temper_placer.router_v6.topology_copper_audit import audit_topology_vs_copper

        net_pins = {n.name: list(n.pins) for n in netlist.nets}
        audit = audit_topology_vs_copper(result.topology_solved_nets, content, net_pins)
        copper_audit_report = audit.format_report()
        unexplained_copper_gap = audit.unexplained_gap

    unrouted = len(result.unrouted_nets)
    completion = result.completion_rate
    # RoutingResult exposes completion_rate and unrouted_nets but not the
    # raw attempted/success counts directly (those live on the internal
    # RouterV6Result, stripped by _build_routing_result). Reconstruct them:
    # completion_rate = success / (success + failure), failure == unrouted
    # exactly, so attempted == unrouted / (1 - completion_rate).
    if completion < 1.0:
        attempted = round(unrouted / (1.0 - completion))
    else:
        attempted = unrouted
    routed = attempted - unrouted

    # The printed "routed/attempted (completion%)" denominator is NOT the
    # board's total net count -- it is PathfindingResult.success_count +
    # failure_count, which only ever includes
    # `[n for n in net_order if _should_route(n)]`
    # (_astar_reconstruct.py). `_should_route` excludes power/ground/HV
    # nets from Stage 4's A* entirely (comment: "handled by zone pours,
    # not path routing"), so they never enter this ratio's numerator OR
    # denominator -- not counted as routed, not counted as failed, simply
    # absent. MEASURED on pcb/temper.kicad_pcb (2026-08-08): 12 of 110
    # nets are excluded this way, which is exactly why net_batching's own
    # trace says "110 nets" while this line says ".../98" -- two different
    # universes, silently, with no note that they differ. Reported here so
    # that shift is visible instead of read as attrition.
    total_router_nets = len(netlist.nets)
    should_route_excluded_nets: list[str] = []
    try:
        from temper_placer.router_v6._net_policy import _should_route

        should_route_excluded_nets = sorted(
            n.name for n in netlist.nets if not _should_route(n.name)
        )
    except ImportError:
        pass

    # Pad connectivity -- see audit_pad_connectivity's docstring for why
    # this, not the routed/attempted line above, is the completion number
    # that should be trusted. net_pins feeds the pin-identity/pad-count
    # accounting guard (see that function's docstring).
    net_pins = {n.name: list(n.pins) for n in netlist.nets}
    pad_connectivity = audit_pad_connectivity(content, net_pins) if content else None

    # NetRouteResult (2026-08-16): the router's OWN verified verdicts --
    # computed inside route_pcb() by the always-on Rust preflight over the
    # emitted copper. "connected" here means NetRouteResult::verify_continuity
    # proved it; the post-hoc audit above is the independent cross-check.
    # None means the preflight failed to run (no verdicts exist).
    net_route_results = getattr(result, "net_route_results", None)

    return {
        "wall_s": wall_s,
        "completion_rate": completion,
        "routed": routed,
        "attempted": attempted,
        "unrouted": unrouted,
        "unrouted_nets": list(result.unrouted_nets),
        "segments": segments,
        "vias": vias,
        "zones": zones,
        "routed_pcb_content": content,
        "copper_audit_report": copper_audit_report,
        "unexplained_copper_gap": unexplained_copper_gap,
        "total_router_nets": total_router_nets,
        "should_route_excluded_nets": should_route_excluded_nets,
        "pad_connectivity": pad_connectivity,
        "net_batch_summary": getattr(result, "net_batch_summary", None) or {},
        "net_route_results": net_route_results,
    }


def _format_net_batch_summary(nbs: dict[str, Any]) -> str:
    """Format the net-batching budget/fallback summary for ALWAYS-ON
    printing (not gated behind TEMPER_BATCH_TRACE) -- see
    RoutingResult.net_batch_summary's docstring
    (router_v6/_adapter_types.py) and
    docs/evidence/2026-08-12-board-recipe-reproducibility.md for why
    silent fallback on a wall-clock subprocess timeout
    (net_batching.DEFAULT_SUBPROCESS_TIMEOUT_S, 900s) is the thing this
    makes visible: it did not fire in this task's own repeated-run
    measurements, but a time-limited subprocess is nondeterministic by
    construction under machine load, so a caller needs a way to tell
    "the board changed because the recipe changed" from "the board
    changed because a batch ran out of time on a loaded machine" without
    re-deriving it from raw stderr each time.
    """
    n = nbs["n_batches"]
    lines = [
        f"[net-batching] {n} batch(es), "
        f"{nbs['n_batches_solved_at_batch_level']} solved at batch level, "
        f"{nbs['n_batches_crashed']} crashed "
        f"({nbs['n_batches_timed_out']} hit the subprocess wall-clock "
        f"timeout, {nbs['n_batches_crashed_other_reason']} crashed another way)"
    ]
    if nbs["n_batches_timed_out"]:
        lines.append(
            f"[net-batching] TIMED OUT batch indices: {nbs['timed_out_batch_indices']} "
            "-- these fell back to singleton retry under a possibly-loaded "
            "machine; a re-run's board is not guaranteed to match this one "
            "for the nets in these batches"
        )
    if nbs["other_crash_reasons"]:
        lines.append(f"[net-batching] other crash reasons: {nbs['other_crash_reasons']}")
    if nbs["n_nets_singleton_retried"]:
        lines.append(
            f"[net-batching] {nbs['n_nets_singleton_retried']} net(s) needed "
            f"singleton retry ({nbs['n_nets_crashed_at_singleton_too']} of "
            "those crashed again at singleton granularity)"
        )
    if nbs["n_nets_no_topology"]:
        lines.append(
            f"[net-batching] {nbs['n_nets_no_topology']} net(s) got NO Stage 3 "
            f"topology (fell through to Stage 4's existing no-topology "
            f"fallback): {', '.join(nbs['nets_no_topology'])}"
        )
    return "\n".join(lines)


def _format_run(label: str, r: dict[str, Any]) -> str:
    line = (
        f"{label}: {r['routed']}/{r['attempted']} nets "
        f"({r['completion_rate'] * 100:.1f}%)  "
        f"segments={r['segments']} vias={r['vias']} zones={r['zones']}  "
        f"wall={r['wall_s']:.1f}s"
    )
    nbs = r.get("net_batch_summary")
    if nbs:
        line += "\n" + _format_net_batch_summary(nbs)
    pc = r.get("pad_connectivity")
    if pc:
        # The PRIMARY completion metric -- see audit_pad_connectivity's
        # docstring. Printed alongside (not replacing) the raw line above so
        # a fake-completion gap between the two is visible in normal output.
        line += (
            f"\n{label} (pad connectivity, PRIMARY metric): "
            f"{pc['fully_connected']}/{pc['audited']} nets fully pad-connected  "
            f"fake-completion={pc['fake_completion']} honest-gap={pc['honest_gap']}"
        )
        mismatches = pc.get("pin_identity_mismatches")
        if mismatches:
            # See audit_pad_connectivity's docstring / pad_connectivity_audit.
            # find_pin_identity_pad_mismatches -- a net whose pin-identity
            # view claims <=1 distinct pin while its real physical pad
            # count is >1 is NOT accounted for by "routed" or "unrouted"
            # above (Stage 4 can print "routed successfully" for it while
            # emitting zero connecting copper). Printed unconditionally,
            # not gated behind an allowlist, so this command's own output
            # can never go quiet about it.
            line += (
                f"\n{label} WARNING -- pin-identity/pad-count mismatch "
                f"({len(mismatches)}, see "
                "pad_connectivity_audit.find_pin_identity_pad_mismatches): "
                f"{', '.join(mismatches)}"
            )
    nrr = r.get("net_route_results")
    if nrr:
        # The router's OWN Rust-verified verdicts (2026-08-16): "connected"
        # is only reachable through NetRouteResult::verify_continuity, so
        # every net below is classified by actual copper continuity, never
        # by "A* found a grid path". Printed unconditionally when present;
        # None (preflight failed to run) prints nothing rather than a
        # fabricated number.
        connected = sorted(n for n, v in nrr.items() if v.disposition == "connected")
        partial = sorted(n for n, v in nrr.items() if v.disposition == "partial")
        zone_dep = sorted(n for n, v in nrr.items() if v.disposition == "zone_dependent")
        failed = sorted(n for n, v in nrr.items() if v.disposition == "failed")
        line += (
            f"\n{label} (verified copper, NetRouteResult): "
            f"{len(connected)} connected, {len(zone_dep)} zone-dependent, "
            f"{len(partial)} partial, {len(failed)} failed "
            f"of {len(nrr)} pad-bearing nets"
        )
        if partial:
            line += f"\n  partial (copper exists, pads NOT all joined): {', '.join(partial)}"
        if zone_dep:
            line += f"\n  zone-dependent (outline only, no fill): {', '.join(zone_dep)}"
    return line


def run_single(
    pcb_path: Path,
    rules_path: Path,
    output_path: Path,
    *,
    enable_geographic_pruning: bool = False,
    enable_net_batching: bool = False,
    net_batch_size: int = 10,
    max_sat_nets: int | None = None,
    enable_nlayer_astar_spike: bool = False,
) -> int:
    print(f"Routing {pcb_path} ...")
    r = route_once(
        pcb_path,
        rules_path,
        enable_geographic_pruning=enable_geographic_pruning,
        enable_net_batching=enable_net_batching,
        net_batch_size=net_batch_size,
        max_sat_nets=max_sat_nets,
        enable_nlayer_astar_spike=enable_nlayer_astar_spike,
    )
    print(_format_run("Result", r))
    if r["unrouted_nets"]:
        print(f"Unrouted ({r['unrouted']}): {', '.join(sorted(r['unrouted_nets']))}")
    if r["should_route_excluded_nets"]:
        n_excl = len(r["should_route_excluded_nets"])
        print(
            f"Note: the {r['attempted']}-net denominator above is "
            f"{r['total_router_nets']} total nets minus {n_excl} excluded "
            f"from Stage 4's A* entirely by _should_route() (power/ground/HV "
            f"nets, presumed zone-covered) -- not counted as routed or "
            f"failed: {', '.join(r['should_route_excluded_nets'])}"
        )
    if r["copper_audit_report"]:
        print(r["copper_audit_report"])
    pc = r.get("pad_connectivity")
    if pc and pc["fake_completion_nets"]:
        print(
            f"Fake-completion nets ({pc['fake_completion']}, copper exists but "
            f"does not join all of the net's own pads -- the b39b382d shape): "
            f"{', '.join(pc['fake_completion_nets'])}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(r["routed_pcb_content"], encoding="utf-8")

    # Propagate pcb_path's project (rules, severities) onto the routed
    # output under ITS OWN stem, so `make drc` / any kicad-cli DRC run
    # against output_path resolves a project instead of silently dropping
    # the project's creepage/track_width/missing_courtyard/annular_width
    # categories. Without this, a routed board written outside pcb/ (e.g.
    # pcb/temper_routed.kicad_pcb, which has no temper_routed.kicad_pro of
    # its own) measures a strict, silent subset of the real violations --
    # see docs/evidence/2026-08-08-drc-project-context-audit.md. Best-effort:
    # if pcb_path itself has no project (e.g. a bare benchmark fixture),
    # there is nothing to propagate and DRC on the output will (correctly)
    # refuse to run blind rather than this script refusing to route.
    try:
        from temper_placer.validation._drc_api import copy_kicad_project_sidecar

        copy_kicad_project_sidecar(output_path, pcb_path)
        print(f"Propagated {pcb_path.with_suffix('.kicad_pro').name} onto {output_path.name}")
    except FileNotFoundError as e:
        print(
            f"WARNING: could not give {output_path} a resolvable KiCad project "
            f"({e}) -- a kicad-cli DRC run against it will refuse to run blind "
            f"rather than silently under-measure. See "
            f"docs/evidence/2026-08-08-drc-project-context-audit.md."
        )

    print(f"Wrote routed board to {output_path}")
    return 0


def _run_worker_subprocess(
    pcb_path: Path,
    rules_path: Path,
    *,
    enable_geographic_pruning: bool = False,
    enable_net_batching: bool = False,
    net_batch_size: int = 10,
    max_sat_nets: int | None = None,
) -> dict[str, Any]:
    """Run one route_once() in a *fresh child process* and return its result.

    Deliberately a subprocess, not an in-process loop: the router is always
    invoked as a fresh process launch in production and in every historical
    measurement in this repo's evidence docs (a new `route_pcb()`-calling
    process per route). Some candidate non-determinism sources -- notably
    Rust's default HashMap hasher, which reseeds from OS randomness once per
    process and is completely independent of PYTHONHASHSEED -- only vary
    *across* process launches. An in-process loop would silently fail to
    reproduce that class of variance and understate (or hide entirely) the
    real spread. This makes --runs N launch N independent processes, each
    inheriting the caller's environment (so `PYTHONHASHSEED=0 ... --runs N`
    pins it identically in every child).

    ``enable_net_batching``/``net_batch_size`` forward --net-batching/
    --batch-size to the worker (previously silently dropped -- --runs N
    --net-batching looked like it measured the net-batching recipe's
    reproducibility but always exercised the monolithic path instead; see
    docs/evidence/2026-08-12-board-recipe-reproducibility.md).
    """
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False
    ) as tmp:
        out_path = Path(tmp.name)
    try:
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--_worker-output", str(out_path),
            "--pcb", str(pcb_path),
            "--rules", str(rules_path),
        ]
        if enable_geographic_pruning:
            cmd.append("--pruning")
        if enable_net_batching:
            cmd += ["--net-batching", "--batch-size", str(net_batch_size)]
        if max_sat_nets is not None:
            cmd += ["--max-sat-nets", str(max_sat_nets)]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"worker subprocess failed (exit {proc.returncode}):\n"
                f"stdout tail:\n{proc.stdout[-2000:]}\n"
                f"stderr tail:\n{proc.stderr[-2000:]}"
            )
        return json.loads(out_path.read_text(encoding="utf-8"))
    finally:
        out_path.unlink(missing_ok=True)


def run_measurement(
    pcb_path: Path,
    rules_path: Path,
    n: int,
    *,
    enable_geographic_pruning: bool = False,
    enable_net_batching: bool = False,
    net_batch_size: int = 10,
    max_sat_nets: int | None = None,
) -> int:
    hashseed = os.environ.get("PYTHONHASHSEED")
    print(
        f"Routing {pcb_path} {n} time(s) from identical input, each run a "
        f"fresh process (PYTHONHASHSEED={hashseed!r}, "
        f"pruning={enable_geographic_pruning}, net_batching={enable_net_batching}"
        + (f", batch_size={net_batch_size}" if enable_net_batching else "")
        + (f", max_sat_nets={max_sat_nets}" if max_sat_nets is not None else "")
        + ") ..."
    )
    completions: list[float] = []
    routed_counts: list[int] = []
    unrouted_sets: list[frozenset[str]] = []
    segment_counts: list[int] = []
    via_counts: list[int] = []
    zone_counts: list[int] = []
    for i in range(1, n + 1):
        r = _run_worker_subprocess(
            pcb_path,
            rules_path,
            enable_geographic_pruning=enable_geographic_pruning,
            enable_net_batching=enable_net_batching,
            net_batch_size=net_batch_size,
            max_sat_nets=max_sat_nets,
        )
        completions.append(r["completion_rate"])
        routed_counts.append(r["routed"])
        unrouted_sets.append(frozenset(r["unrouted_nets"]))
        segment_counts.append(r["segments"])
        via_counts.append(r["vias"])
        zone_counts.append(r["zones"])
        print(_format_run(f"Run {i}/{n}", r))

    lo, hi = min(completions), max(completions)
    lo_n, hi_n = min(routed_counts), max(routed_counts)
    print()
    print(
        f"Spread across {n} run(s): completion {lo * 100:.1f}%-{hi * 100:.1f}% "
        f"({(hi - lo) * 100:+.1f} pt range), routed-net count {lo_n}-{hi_n} "
        f"({hi_n - lo_n} net swing)"
    )
    print(
        f"Copper spread: segments {min(segment_counts)}-{max(segment_counts)}, "
        f"vias {min(via_counts)}-{max(via_counts)}, "
        f"zones {min(zone_counts)}-{max(zone_counts)} "
        "-- more telling than the completion percentage above: two runs can "
        "agree on completion% while routing materially different copper."
    )
    if n > 1:
        print(f"stdev(completion_rate) = {statistics.pstdev(completions):.4f}")
    same_set = len(set(unrouted_sets)) <= 1
    same_copper_counts = (
        min(segment_counts) == max(segment_counts)
        and min(via_counts) == max(via_counts)
        and min(zone_counts) == max(zone_counts)
    )
    if hi_n == lo_n and same_set and same_copper_counts:
        print(
            "All runs identical -- no variance observed (same completion, "
            "same failed-net set, same segment/via/zone counts)."
        )
    elif hi_n == lo_n and not same_set:
        print(
            "Completion COUNT identical across runs, but the SPECIFIC "
            "failed-net set differs between runs -- which nets route is "
            "non-deterministic even though how many route is not."
        )
    elif hi_n == lo_n and same_set and not same_copper_counts:
        print(
            "Completion and failed-net set identical across runs, but "
            "segment/via/zone COUNTS differ -- the same nets complete but "
            "route through different geometry run to run."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pcb", type=Path, default=DEFAULT_PCB,
        help=f"Path to .kicad_pcb file to route (default: {DEFAULT_PCB.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--rules", type=Path, default=DEFAULT_RULES,
        help=f"Path to netclass_rules.yaml (default: {DEFAULT_RULES.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help=(
            "Write the routed .kicad_pcb here. Required in single-route mode "
            "(no default -- this driver never overwrites the input board "
            "implicitly). Ignored in --runs mode, which writes nothing."
        ),
    )
    parser.add_argument(
        "--runs", type=int, default=None, metavar="N",
        help=(
            "Route N times from identical input, each in a fresh process, "
            "and report the per-run completion figure, segment/via/zone "
            "spread, and the spread across runs. Measurement only -- does "
            "not write any output file. Honors --net-batching/--batch-size "
            "(each worker process gets the same flags)."
        ),
    )
    parser.add_argument(
        "--_worker-output", type=Path, default=None,
        help=argparse.SUPPRESS,  # internal: used by --runs's own subprocess dispatch
    )
    parser.add_argument(
        "--pruning", action="store_true",
        help=(
            "Pass enable_geographic_pruning=True to route_pcb() (U5 of "
            "docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md). "
            "Default False -- unchanged full-encoding behavior."
        ),
    )
    parser.add_argument(
        "--net-batching",
        dest="net_batching",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Pass enable_net_batching=True to route_pcb() (`#871` net-"
            "batching, see router_v6/net_batching.py). Default False since "
            "2026-08-16 (reverted from #1250's True): the monolithic path "
            "no longer OOMs -- Stage 3's default is the direct capacity-"
            "aware topology solver (docs/evidence/2026-08-16-sat-capacity-"
            "vacuity-fix.md), which builds no SAT model at all and measures "
            "96/139 pad-connected in ~291s vs the batched vacuous SAT's "
            "92/139 in ~485s. Pass --net-batching for the legacy batched "
            "SAT recipe (still the measured 92/139 reference)."
        ),
    )
    parser.add_argument(
        "--batch-size", type=int, default=10,
        help="Nets per Stage 3 SAT batch when --net-batching is set (default 10).",
    )
    parser.add_argument(
        "--max-sat-nets", type=int, default=None,
        help=(
            "Selective SAT: encode only the top-N nets (ascending pin "
            "count) into the Stage 3 model; every other net falls through "
            "to Stage 4's unguided A* fallback. Caps the |nets| x |edges| "
            "CNF term (the 2026-08-15 Stage 3 memory-blowup fix). Default "
            "None -- encode every net. Ignored when --net-batching is set "
            "(batching takes priority in _run_stage3)."
        ),
    )
    parser.add_argument(
        "--nlayer-astar-spike", action="store_true",
        help=(
            "Pass enable_nlayer_astar_spike=True to route_pcb() -- routes "
            "Stage 4 through the N-layer, via-aware A* spike prototype "
            "(_astar_nlayer.py, spike/nlayer-via-astar branch) instead of "
            "the production 2-layer-capped path. Default False -- "
            "unchanged production behavior. See "
            "docs/evidence/2026-08-08-nlayer-via-astar-spike.md."
        ),
    )
    args = parser.parse_args(argv)

    if not args.pcb.exists():
        parser.error(f"PCB file not found: {args.pcb}")
    if not args.rules.exists():
        parser.error(f"Netclass rules file not found: {args.rules}")

    if args._worker_output is not None:
        r = route_once(
            args.pcb,
            args.rules,
            enable_geographic_pruning=args.pruning,
            enable_net_batching=args.net_batching,
            net_batch_size=args.batch_size,
            max_sat_nets=args.max_sat_nets,
            enable_nlayer_astar_spike=args.nlayer_astar_spike,
        )
        r.pop("routed_pcb_content", None)
        args._worker_output.write_text(json.dumps(r), encoding="utf-8")
        return 0

    if args.runs is not None:
        if args.runs < 1:
            parser.error("--runs must be >= 1")
        return run_measurement(
            args.pcb,
            args.rules,
            args.runs,
            enable_geographic_pruning=args.pruning,
            enable_net_batching=args.net_batching,
            net_batch_size=args.batch_size,
            max_sat_nets=args.max_sat_nets,
        )

    if args.output is None:
        parser.error(
            "--output PATH is required. Routing output on a mains-connected "
            "board is reviewed before it lands -- this driver refuses to "
            "guess a default and overwrite anything implicitly. Use --runs N "
            "for measurement-only mode, which writes nothing."
        )

    if args.output.resolve() == args.pcb.resolve():
        parser.error(
            f"--output must not be the same path as --pcb ({args.pcb}). "
            "This driver refuses to overwrite the input board, ever."
        )

    return run_single(
        args.pcb,
        args.rules,
        args.output,
        enable_geographic_pruning=args.pruning,
        enable_net_batching=args.net_batching,
        net_batch_size=args.batch_size,
        max_sat_nets=args.max_sat_nets,
        enable_nlayer_astar_spike=args.nlayer_astar_spike,
    )


if __name__ == "__main__":
    sys.exit(main())
