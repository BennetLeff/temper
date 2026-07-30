#!/usr/bin/env python3
"""Route a KiCad PCB through the router_v6 production entry point.

This is the working entry point that ``make route`` and
``scripts/internal_route.py`` are not: ``make route`` targets the
33-net benchmark fixture (``pcb/benchmarks/temper_fixture_33.kicad_pcb``),
and ``internal_route.py`` imports the superseded ``temper_placer.routing.*``
tree plus an undeclared ``jax`` dependency and cannot be imported at all.

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
strip_existing_copper in temper_placer.router_v6._strip_copper), so any
zones present in the output are this run's own regenerated output, never
carried-over stale input.
"""
from __future__ import annotations

import argparse
import hashlib
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
    ``temper_placer.router_v6._strip_copper`` -- kept as a module-level name
    here (rather than only inlined in ``route_once``) so this remains
    directly importable/testable as ``route_board.strip_existing_copper``,
    matching this script's prior art. The import itself is deferred inside
    this function body, not hoisted to module scope: importing any
    ``temper_placer.router_v6`` submodule executes that package's full
    ``__init__.py`` (numba, the Rust router extension, etc.), which this
    script otherwise avoids paying for argument parsing / ``--help``.

    Previously this was its own single-line ``re.MULTILINE`` regex matching
    only ``(segment ...)``/``(via ...)`` -- a pattern that could never have
    matched a ``(zone ...)`` block, which is not single-line (see
    ``pcb/temper.kicad_pcb``: every zone spans dozens of lines --
    ``priority``, ``connect_pads``, ``min_thickness``, ``fill``, and a
    nested ``(polygon (pts (xy ..) ...))``). That is why every "clean"
    re-route still inherited all 96 committed zones.
    """
    from temper_placer.router_v6._strip_copper import (
        strip_existing_copper as _strip_existing_copper,
    )

    return _strip_existing_copper(content)


def route_once(
    pcb_path: Path, rules_path: Path, *, keep_existing_copper: bool = False
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
    )
    wall_s = time.perf_counter() - t0

    content = result.routed_pcb_content or ""
    segments = content.count("(segment ")
    vias = content.count("(via ")
    zones = content.count("(zone ")

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
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "routed_pcb_content": content,
    }


def _format_run(label: str, r: dict[str, Any]) -> str:
    return (
        f"{label}: {r['routed']}/{r['attempted']} nets "
        f"({r['completion_rate'] * 100:.1f}%)  "
        f"segments={r['segments']} vias={r['vias']} zones={r['zones']}  "
        f"wall={r['wall_s']:.1f}s"
    )


def outputs_are_identical(content_hashes: list[str]) -> bool:
    """Return whether every full emitted-board hash is identical."""
    return len(set(content_hashes)) <= 1


def run_single(pcb_path: Path, rules_path: Path, output_path: Path) -> int:
    print(f"Routing {pcb_path} ...")
    r = route_once(pcb_path, rules_path)
    print(_format_run("Result", r))
    if r["unrouted_nets"]:
        print(f"Unrouted ({r['unrouted']}): {', '.join(sorted(r['unrouted_nets']))}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(r["routed_pcb_content"], encoding="utf-8")
    print(f"Wrote routed board to {output_path}")
    return 0


def _run_worker_subprocess(pcb_path: Path, rules_path: Path) -> dict[str, Any]:
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
    """
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False
    ) as tmp:
        out_path = Path(tmp.name)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--_worker-output", str(out_path),
                "--pcb", str(pcb_path),
                "--rules", str(rules_path),
            ],
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


def run_measurement(pcb_path: Path, rules_path: Path, n: int) -> int:
    hashseed = os.environ.get("PYTHONHASHSEED")
    print(
        f"Routing {pcb_path} {n} time(s) from identical input, each run a "
        f"fresh process (PYTHONHASHSEED={hashseed!r}) ..."
    )
    completions: list[float] = []
    routed_counts: list[int] = []
    unrouted_sets: list[frozenset[str]] = []
    content_hashes: list[str] = []
    for i in range(1, n + 1):
        r = _run_worker_subprocess(pcb_path, rules_path)
        completions.append(r["completion_rate"])
        routed_counts.append(r["routed"])
        unrouted_sets.append(frozenset(r["unrouted_nets"]))
        content_hashes.append(r["content_sha256"])
        print(_format_run(f"Run {i}/{n}", r))

    lo, hi = min(completions), max(completions)
    lo_n, hi_n = min(routed_counts), max(routed_counts)
    print()
    print(
        f"Spread across {n} run(s): completion {lo * 100:.1f}%-{hi * 100:.1f}% "
        f"({(hi - lo) * 100:+.1f} pt range), routed-net count {lo_n}-{hi_n} "
        f"({hi_n - lo_n} net swing)"
    )
    if n > 1:
        print(f"stdev(completion_rate) = {statistics.pstdev(completions):.4f}")
    same_set = len(set(unrouted_sets)) <= 1
    same_content = outputs_are_identical(content_hashes)
    if hi_n == lo_n and same_set and same_content:
        print(
            "All runs identical -- no variance observed (same completion, "
            "failed-net set, and emitted-board SHA-256)."
        )
    elif hi_n == lo_n and not same_set:
        print(
            "Completion COUNT identical across runs, but the SPECIFIC "
            "failed-net set differs between runs -- which nets route is "
            "non-deterministic even though how many route is not."
        )
    if not same_content:
        print(
            "FAIL: emitted-board content differs across identical-input runs "
            f"({len(set(content_hashes))} distinct SHA-256 values)."
        )
        return 1
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
            "and report the per-run completion figure plus the spread "
            "across runs. Measurement only -- does not write any output "
            "file."
        ),
    )
    parser.add_argument(
        "--_worker-output", type=Path, default=None,
        help=argparse.SUPPRESS,  # internal: used by --runs's own subprocess dispatch
    )
    args = parser.parse_args(argv)

    if not args.pcb.exists():
        parser.error(f"PCB file not found: {args.pcb}")
    if not args.rules.exists():
        parser.error(f"Netclass rules file not found: {args.rules}")

    if args._worker_output is not None:
        r = route_once(args.pcb, args.rules)
        r.pop("routed_pcb_content", None)
        args._worker_output.write_text(json.dumps(r), encoding="utf-8")
        return 0

    if args.runs is not None:
        if args.runs < 1:
            parser.error("--runs must be >= 1")
        return run_measurement(args.pcb, args.rules, args.runs)

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

    return run_single(args.pcb, args.rules, args.output)


if __name__ == "__main__":
    sys.exit(main())
